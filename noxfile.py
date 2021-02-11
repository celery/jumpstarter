import functools
import glob
from pathlib import Path
from typing import Any, Optional

import nox
from nox_poetry import Session
from nox_poetry.poetry import Config, Poetry
from nox_poetry.sessions import _PoetrySession

# TODO: remove all customizations when https://github.com/cjolowicz/nox-poetry/issues/276 is fixed


class JumpstarterConfig(Config):
    def __init__(self, *args, extras: Optional[list] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._extras = extras

    @property
    def extras(self):
        extras = super().extras

        if self._extras is not None:
            return [extra for extra in extras if extra in self._extras]

        return extras


class JumpstarterPoetry(Poetry):
    def __init__(self, *args, extras: Optional[list] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extras = extras

    @property
    def config(self) -> Config:
        """Return the package configuration."""
        if self._config is None:
            self._config = JumpstarterConfig(Path.cwd(), extras=self.extras)
        return self._config


class JumpstarterSession(_PoetrySession):
    def __init__(self, session: nox.Session, extras: Optional[list] = None) -> None:
        """Initialize."""
        self.session = session
        self.poetry: Poetry = JumpstarterPoetry(session, extras=extras)


def session(*args: Any, **kwargs: Any) -> Any:
    """Drop-in replacement for the :func:`nox.session` decorator.

    Use this decorator instead of ``@nox.session``. Session functions are passed
    :class:`Session` instead of :class:`nox.sessions.Session`; otherwise, the
    decorators work exactly the same.

    Args:
        args: Positional arguments are forwarded to ``nox.session``.
        kwargs: Keyword arguments are forwarded to ``nox.session``.

    Returns:
        The decorated session function.
    """
    if not args:
        return functools.partial(session, **kwargs)

    [function] = args

    extras = kwargs.pop("extras", None)

    @functools.wraps(function)
    def wrapper(session: nox.Session, *_args, **_kwargs) -> None:
        proxy = JumpstarterSession(session, extras=extras)
        function(proxy, *_args, **_kwargs)

    return nox.session(wrapper, **kwargs)


@session
def build_docs(session: Session):
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("sphinx-autodoc", "-e", "-T", "jumpstarter/", "-o", "docs/reference")
    session.run(
        "sphinx-build", "-b", "html", "-j", "auto", "docs/", "docs/_build/_html"
    )


@session(python=("3.7", "3.8", "3.9"), extras=[])
def test(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run(
        "pytest", "-nauto", "--cov=jumpstarter", "--cov-branch", "--cov-report=xml"
    )


@session
def retype(session: Session) -> None:
    """Run the test suite."""
    session.install(".")
    session.run("poetry", "install", external=True)
    session.run("pytest", "--monkeytype-output=./monkeytype.sqlite3", silent=True)
    result = session.run("monkeytype", "list-modules", silent=True)
    results = [module for module in result.split("\n") if "jumpstarter." in module]

    for result in results:
        session.run("monkeytype", "apply", result)


@session
def format(session: Session) -> None:
    session.install(".")
    session.run("poetry", "install", external=True)

    session.log("Upgrade code to Python 3.7+")
    for file in glob.glob("./**/*.py", recursive=True):
        session.log(f"Upgrading {file}")
        session.run(
            "pyupgrade",
            "--py37-plus",
            "--exit-zero-even-if-changed",
            "--keep-mock",
            file,
        )

    session.log("Removing unused imports and variables")
    session.run(
        "autoflake",
        "--verbose",
        "-r",
        "-i",
        "--remove-unused-variables",
        "--remove-all-unused-imports",
        "--exclude",
        "tests/mock.py",
        "--ignore-init-module-imports",
        "jumpstarter/",
        "tests/",
    )

    session.log("Sorting imports")
    session.run("isort", "jumpstarter/", "tests/")

    session.log("Reformatting code")
    session.run("black", "jumpstarter/", "tests/")

    session.log("Sorting pyproject.toml")
    session.run("toml-sort", "-i", "--all", "pyproject.toml")
