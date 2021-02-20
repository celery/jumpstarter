import pytest

from jumpstarter import Actor
from jumpstarter.actors import (
    UnsatisfiedDependencyError,
    DependencyAlreadySatisfiedError,
)
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


async def test_dependency_already_satisfied():
    class FakeActor(Actor):
        ...

    class FakeActor2(Actor, dependencies=[FakeActor]):
        ...

    fake_actor = FakeActor()
    fake_actor2 = FakeActor2()

    fake_actor2.satisfy_dependency(fake_actor)

    with pytest.raises(
        DependencyAlreadySatisfiedError,
        match=r"tests.actors.test_actor_dependencies.test_dependency_already_satisfied.<locals>.FakeActor is already satisfied by <tests.actors.test_actor_dependencies.test_dependency_already_satisfied.<locals>.FakeActor object at 0x[0-9a-f]+>",
    ):
        fake_actor2.satisfy_dependency(fake_actor)


async def test_start_stop_dependencies(subtests):
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
    fake_actor3.satisfy_dependency(fake_actor)

    await fake_actor3.start()

    with subtests.test("all dependencies are started"):
        assert fake_actor.state == ActorRunningState.healthy
        assert fake_actor2.state == {
            "test_start_stop_dependencies.<locals>.FakeActor": ActorRunningState.healthy,
            "test_start_stop_dependencies.<locals>.FakeActor2": ActorRunningState.healthy,
        }
        assert fake_actor3.state == {
            "test_start_stop_dependencies.<locals>.FakeActor2": {
                "test_start_stop_dependencies.<locals>.FakeActor": ActorRunningState.healthy,
                "test_start_stop_dependencies.<locals>.FakeActor2": ActorRunningState.healthy,
            },
            "test_start_stop_dependencies.<locals>.FakeActor3": ActorRunningState.healthy,
        }

    await fake_actor3.stop()

    with subtests.test("all dependencies are stopped"):
        assert fake_actor.state == ActorState.stopped
        assert fake_actor2.state == {
            "test_start_stop_dependencies.<locals>.FakeActor": ActorState.stopped,
            "test_start_stop_dependencies.<locals>.FakeActor2": ActorState.stopped,
        }
        assert fake_actor3.state == {
            "test_start_stop_dependencies.<locals>.FakeActor2": {
                "test_start_stop_dependencies.<locals>.FakeActor": ActorState.stopped,
                "test_start_stop_dependencies.<locals>.FakeActor2": ActorState.stopped,
            },
            "test_start_stop_dependencies.<locals>.FakeActor3": ActorState.stopped,
        }


async def test_cannot_satisfy_dependency():
    class FakeActor(Actor):
        ...

    class FakeActor2(Actor, dependencies=[FakeActor]):
        ...

    fake_actor = FakeActor2()

    with pytest.raises(
        TypeError,
        match=r"builtins.object cannot satisfy any of the following dependencies:\n"
        "tests.actors.test_actor_dependencies.test_cannot_satisfy_dependency.<locals>.FakeActor",
    ):
        fake_actor.satisfy_dependency(object())


async def test_unsatisfied_dependency():
    class FakeActor(Actor):
        ...

    class FakeActor2(Actor, dependencies=[FakeActor]):
        ...

    fake_actor = FakeActor2()

    with pytest.raises(UnsatisfiedDependencyError) as e:
        await fake_actor.start()

    assert e.value.args[0] is FakeActor
