import pytest

from jumpstarter import Actor
from jumpstarter.states import ActorRunningState, ActorState

pytestmark = pytest.mark.anyio


async def test_actor_is_present_in_the_dependency_graph():
    class FakeActor(Actor):
        ...

    assert FakeActor in Actor._Actor__dependency_graph


async def test_invalid_dependencies():
    with pytest.raises(
        TypeError,
        match=r"The following dependencies are not actors and therefore invalid:\nbuiltins.object",
    ):

        class FakeActor(Actor, dependencies=[object]):
            ...


async def test_dependency_graph():
    class FakeActor(Actor):
        ...

    class FakeActor2(Actor, dependencies=[FakeActor]):
        ...

    class FakeActor3(Actor, dependencies=[FakeActor2, FakeActor]):
        ...

    assert FakeActor3.dependencies == {FakeActor2}


async def test_start_stop_dependencies():
    class FakeActor(Actor):
        ...

    class FakeActor2(Actor, dependencies=[FakeActor]):
        ...

    class FakeActor3(Actor, dependencies=[FakeActor2, FakeActor]):
        ...

    fake_actor = FakeActor()
    fake_actor2 = FakeActor2()
    fake_actor3 = FakeActor3()
    fake_actor3.satisfy_dependency(fake_actor2)
    fake_actor2.satisfy_dependency(fake_actor)

    await fake_actor3.start()

    assert fake_actor.state == ActorRunningState.healthy
    assert fake_actor2.state == ActorRunningState.healthy
    assert fake_actor3.state == ActorRunningState.healthy

    await fake_actor3.stop()

    assert fake_actor.state == ActorState.stopped
    assert fake_actor2.state == ActorState.stopped
    assert fake_actor3.state == ActorState.stopped
