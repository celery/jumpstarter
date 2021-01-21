from unittest.mock import MagicMock, sentinel

import anyio
import pytest

from jumpstarter.resources import ThreadedContextManager

pytestmark = pytest.mark.anyio


async def test_threaded_context_manager(subtests):
    context_manager = MagicMock()
    context_manager.__enter__.return_value = sentinel.RETURN_VALUE

    threaded_context_manager = ThreadedContextManager(
        context_manager, anyio.create_capacity_limiter(1)
    )

    with subtests.test("threaded context manager is proxied"):
        assert isinstance(threaded_context_manager, MagicMock)

    with subtests.test("__enter__ is called in a worker thread"):
        async with threaded_context_manager as m:
            context_manager.__enter__.assert_called_once_with()

    with subtests.test("__enter__'s return value is returned"):
        assert m == sentinel.RETURN_VALUE

    with subtests.test("__exit__ is called in a worker thread"):
        context_manager.__exit__.assert_called_once_with(None, None, None)


async def test_threaded_context_manager_raises_exception(subtests):
    class ExpectedException(Exception):
        pass

    context_manager = MagicMock()
    context_manager.__enter__.side_effect = ExpectedException

    threaded_context_manager = ThreadedContextManager(
        context_manager, anyio.create_capacity_limiter(1)
    )

    with subtests.test("exception is raised from __enter__"):
        with pytest.raises(ExpectedException):
            async with threaded_context_manager:
                pass

    context_manager.__enter__.side_effect = None
    context_manager.__exit__.return_value = True

    with subtests.test(
        "exception is suppressed from __enter__ since __exit__ returns True"
    ):
        async with threaded_context_manager:
            raise ExpectedException()
