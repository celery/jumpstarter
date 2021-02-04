import anyio
import pytest

from jumpstarter.actors import Actor
from jumpstarter.resources import (NotAResourceError, ResourceUnavailable,
                                   resource)
from jumpstarter.states import ActorRunningState, ActorState
from tests.mock import AsyncMock, MagicMock, sentinel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("resource_type",),
    (
        pytest.param(MagicMock, id="sync resource"),
        pytest.param(AsyncMock, id="async resource"),
    ),
)
async def test_acquire_resource(subtests, resource_type):
    resource_mock = resource_type()

    class FakeActor(Actor):
        @resource
        def resource(self):
            return resource_mock

    fake_actor = FakeActor()

    assert fake_actor.state == ActorState.initializing

    async with anyio.create_task_group() as tg:
        await fake_actor.start(tg)

    assert fake_actor.state == ActorRunningState.healthy

    with subtests.test("__aenter__ is called"):
        resource_mock.__aenter__.assert_called_once_with(resource_mock)
        resource_mock.__aexit__.assert_not_called()

    assert fake_actor.state != ActorState.stopped
    await fake_actor.stop()

    with subtests.test("__aexit__ is called"):
        resource_mock.__aexit__.assert_called_once_with(resource_mock, None, None, None)


@pytest.mark.parametrize(
    ("resource_type",),
    (
        pytest.param(MagicMock, id="sync resource"),
        pytest.param(AsyncMock, id="async resource"),
    ),
)
async def test_acquire_resource_within_specified_timeout(subtests, resource_type):
    resource_mock = resource_type()

    class FakeActor(Actor):
        @resource(timeout=1)
        def resource(self):
            return resource_mock

    fake_actor = FakeActor()

    assert fake_actor.state == ActorState.initializing

    async with anyio.create_task_group() as tg:
        await fake_actor.start(tg)

    assert fake_actor.state == ActorRunningState.healthy

    with subtests.test("__aenter__ is called"):
        resource_mock.__aenter__.assert_called_once_with(resource_mock)
        resource_mock.__aexit__.assert_not_called()

    assert fake_actor.state != ActorState.stopped
    await fake_actor.stop()

    with subtests.test("__aexit__ is called"):
        resource_mock.__aexit__.assert_called_once_with(resource_mock, None, None, None)


async def test_acquire_async_resource_timed_out(subtests):
    async def cause_timeout(*_, **__):
        await anyio.sleep(5)

    resource_mock = AsyncMock()
    resource_mock.__aenter__.side_effect = cause_timeout

    class FakeActor(Actor):
        @resource(timeout=0.01)
        def resource(self):
            return resource_mock

    fake_actor = FakeActor()

    with pytest.raises(TimeoutError):
        async with anyio.create_task_group() as tg:
            await fake_actor.start(tg)


async def test_acquire_sync_resource_timeout_not_supported(subtests):
    resource_mock = MagicMock()
    del resource_mock.__aenter__
    del resource_mock.__aexit__

    class FakeActor(Actor):
        @resource(timeout=0.01)
        def resource(self):
            return resource_mock

    fake_actor = FakeActor()

    with pytest.raises(TypeError):
        async with anyio.create_task_group() as tg:
            await fake_actor.start(tg)


async def test_acquire_resource_not_a_resource(subtests):
    class FakeActorWithAFaultyResource(Actor):
        @resource
        def not_a_resource(self):
            return object()

    a = FakeActorWithAFaultyResource()

    with pytest.raises(
        NotAResourceError,
        match=r"The return value of not_a_resource is not a context manager\.\n"
        r"Instead we got <object object at 0x[0-9a-f]+>\.",
    ):
        await a.start()


async def test_acquire_resource_within_specified_timeout_not_a_resource(subtests):
    class FakeActorWithAFaultyResource(Actor):
        @resource(timeout=1)
        def not_a_resource(self):
            return object()

    a = FakeActorWithAFaultyResource()

    with pytest.raises(
        NotAResourceError,
        match=r"The return value of not_a_resource is not a context manager\.\n"
        r"Instead we got <object object at 0x[0-9a-f]+>\.",
    ):
        await a.start()


async def test_resource_is_immutable():
    class FakeActor(Actor):
        @resource
        def resource(self):
            return AsyncMock()

    fake_actor = FakeActor()

    with pytest.raises(AttributeError, match=r"can't set attribute"):
        fake_actor.resource = object()


async def test_resource_accessor(subtests):
    resource_mock = AsyncMock()
    resource_mock.__aenter__.return_value = sentinel.RETURN_VALUE

    class FakeActor(Actor):
        @resource
        def resource(self):
            return resource_mock

    fake_actor = FakeActor()

    await fake_actor.start()

    with subtests.test("resource is accessible once acquired"):
        assert fake_actor.resource is sentinel.RETURN_VALUE

    await fake_actor.stop()

    with subtests.test("resource is None after release"):
        assert fake_actor.resource is None


async def test_resource_unavailable():
    class FakeActor(Actor):
        @resource
        def resource(self):
            raise ResourceUnavailable()

    fake_actor = FakeActor()

    await fake_actor.start()

    assert fake_actor.resource is None
