import pytest

from jumpstarter import Actor

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
