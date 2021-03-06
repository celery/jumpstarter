import nox
import nox_poetry.patch
from nox.sessions import Session


@nox.session
def build_docs(session: Session):
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("sphinx-build", "-b", "html", "-j", "auto", "docs/", "docs/_build/_html")


@nox.session(python=("3.7", "3.8", "3.9"))
def test(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.install("pytest")
    session.run("pytest")


@nox.session
def format(session: Session) -> None:
    session.install("black", "isort")
    session.run("black", "jumpstarter/", "tests/")
    session.run("isort", "jumpstarter/", "tests/")
