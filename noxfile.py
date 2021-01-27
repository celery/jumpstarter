import nox
import nox_poetry.patch
from nox.sessions import Session


@nox.session(python=("3.7", "3.8", "3.9"))
def test(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("pytest", "-nauto")


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
    session.install("black", "isort")
    session.run("black", "jumpstarter/", "tests/")
    session.run("isort", "jumpstarter/", "tests/")
