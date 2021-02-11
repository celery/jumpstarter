import glob

import nox
import nox_poetry.patch  # noqa: F401
from nox.sessions import Session


@nox.session
def build_docs(session: Session):
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("sphinx-autodoc", "-e", "-T", "jumpstarter/", "-o", "docs/reference")
    session.run("sphinx-build", "-b", "html", "-j", "auto", "docs/", "docs/_build/_html")


@nox.session(python=("3.7", "3.8", "3.9"))
def test(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("pytest", "-nauto", "--cov=jumpstarter", "--cov-branch", "--cov-report=xml")


@nox.session
def retype(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("pytest", "--monkeytype-output=./monkeytype.sqlite3", silent=True)
    result = session.run("monkeytype", "list-modules", silent=True)
    results = [module for module in result.split('\n') if 'jumpstarter.' in module]

    for result in results:
        session.run("monkeytype", "apply", result)


@nox.session
def format(session: Session) -> None:
    session.install(".")
    session.run("poetry", "install", external=True)

    session.log("Upgrade code to Python 3.7+")
    for file in glob.glob("./**/*.py", recursive=True):
        session.log(f"Upgrading {file}")
        session.run("pyupgrade", "--py37-plus", "--exit-zero-even-if-changed", "--keep-mock", file)

    session.log("Removing unused imports and variables")
    session.run("autoflake", "--verbose", "-r", "-i", "--remove-unused-variables", "--remove-all-unused-imports",
                "--exclude", "tests/mock.py", "--ignore-init-module-imports", "jumpstarter/", "tests/")

    session.log("Sorting imports")
    session.run("isort", "jumpstarter/", "tests/")

    session.log("Reformatting code")
    session.run("black", "jumpstarter/", "tests/")

    session.log("Sorting pyproject.toml")
    session.run("toml-sort", "-i", "--all", "pyproject.toml")
