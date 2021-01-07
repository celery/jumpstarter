import anyio
import pytest
from mock import AsyncMock

from jumpstarter.actors import Actor
from jumpstarter.resources import NotAResourceError, Resource
from jumpstarter.states import ActorState


class FakeActor(Actor):
    def __init__(self):
        super(FakeActor, self).__init__()
        self.resource_mock = AsyncMock()

    @Resource
    def resource(self):
        return self.resource_mock


@pytest.mark.anyio
async def test_acquire_resource(subtests):
    fake_actor = FakeActor()
    resource_mock = fake_actor.resource_mock
    assert fake_actor.state == ActorState.initializing

    async with anyio.create_task_group() as tg:
        await fake_actor.start(tg)

    assert fake_actor.state == ActorState.started

    with subtests.test("__aenter__ is called"):
        resource_mock.__aenter__.assert_called_once_with(resource_mock)
        resource_mock.__aexit__.assert_not_called()

    assert fake_actor.state != ActorState.stopped
    await fake_actor.stop()

    with subtests.test("__aexit__ is called"):
        resource_mock.__aexit__.assert_called_once_with(resource_mock, None, None, None)


class FakeActorWithAFaultyResource(Actor):
    @Resource
    def not_a_resource(self):
        return object()


@pytest.mark.anyio
async def test_acquire_resource_not_a_resource(subtests):
    a = FakeActorWithAFaultyResource()

    with pytest.raises(
        NotAResourceError,
        match=r"The return value of not_a_resource is not a context manager\.\n"
        r"Instead we got <object object at 0x[0-9a-f]+>\.",
    ):
        await a.start()
