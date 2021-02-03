import pytest

from jumpstarter.actors import Actor
from jumpstarter.resources import resource
from jumpstarter.states import ActorStartingState

pytestmark = pytest.mark.anyio


async def test_child_actors_do_not_share_the_same_callbacks():
    class FakeActor1(Actor):
        @resource
        def foo(self):
            return object()

    class FakeActor2(Actor):
        @resource
        def bar(self):
            return object()

    transition1 = FakeActor1._state_machine.get_transitions("start", ActorStartingState.dependencies_started, ActorStartingState.resources_acquired)[0]
    transition2 = FakeActor2._state_machine.get_transitions("start", ActorStartingState.dependencies_started, ActorStartingState.resources_acquired)[0]
    transition3 = Actor._state_machine.get_transitions("start", ActorStartingState.dependencies_started, ActorStartingState.resources_acquired)[0]

    assert transition1.before is not transition2.before
    assert transition3.before is not transition1.before