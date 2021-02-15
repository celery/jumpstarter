import pytest

from jumpstarter import Actor
from jumpstarter import resource
from jumpstarter.actors import ActorStateMachineFactory
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

    transition1 = FakeActor1._state_machine.get_transitions(
        "start",
        ActorStartingState.dependencies_started,
        ActorStartingState.resources_acquired,
    )[0]
    transition2 = FakeActor2._state_machine.get_transitions(
        "start",
        ActorStartingState.dependencies_started,
        ActorStartingState.resources_acquired,
    )[0]
    transition3 = Actor._state_machine.get_transitions(
        "start",
        ActorStartingState.dependencies_started,
        ActorStartingState.resources_acquired,
    )[0]

    assert transition1.before is not transition2.before
    assert transition3.before is not transition1.before


async def test_resource_inheritance():
    class FakeActor1(Actor):
        @resource
        def foo(self):
            return object()

    class FakeActor2(FakeActor1):
        @resource
        def bar(self):
            return object()

    transition = FakeActor2._state_machine.get_transitions(
        "start",
        ActorStartingState.dependencies_started,
        ActorStartingState.resources_acquired,
    )[0]

    assert [f.__qualname__ for f in transition.before] == [
        "Actor.cancel_scope",
        "test_resource_inheritance.<locals>.FakeActor1.foo",
        "test_resource_inheritance.<locals>.FakeActor2.bar",
    ]


async def test_actor_state_must_be_of_the_correct_type():
    with pytest.raises(
        TypeError,
        match="Actor states must be ActorState or a child class of it. Instead we got object.",
    ):

        class FakeActor(Actor, actor_state=object):
            ...


# TODO: Figure out how to resolve actor state extension.
# async def test_child_actor_state_must_be_the_same_as_the_parent_actor_state():
#     class BaseActor(Actor):
#         ...
#
#     class SpecialActorState(ActorState):
#         pass
#
#     with pytest.raises(
#             TypeError,
#             match="",
#     ):
#         class ChildActor(BaseActor, actor_state=SpecialActorState):
#             ...


async def test_same_state_machine_is_returned_for_each_actor(subtests):
    class FakeActor1(Actor):
        ...

    class FakeActor2(Actor):
        ...

    factory = ActorStateMachineFactory()

    m1 = factory[FakeActor1]
    with subtests.test("The same state machine is returned once created (FakeActor1)"):
        assert m1 is factory[FakeActor1]
    with subtests.test("The new state machine is now cached (FakeActor1)"):
        assert len(list(factory.values())) == 1

    m2 = factory[FakeActor2]
    with subtests.test("The same state machine is returned once created (FakeActor2)"):
        assert m2 is factory[FakeActor2]
    with subtests.test("The new state machine is now cached (FakeActor2)"):
        assert len(list(factory.values())) == 2

    with subtests.test(
        "The new state machine for FakeActor1 is not the same as the one for FakeActor2"
    ):
        assert m1 is not m2


async def test_no_base_actor_type_error():
    factory = ActorStateMachineFactory()
    with pytest.raises(TypeError, match="No base actor found."):
        _ = factory[object]


async def test_only_single_inheritance_is_supported():
    class BaseActor1(Actor):
        ...

    class BaseActor2(Actor):
        ...

    class FakeActor(BaseActor1, BaseActor2):
        pass

    factory = ActorStateMachineFactory()
    with pytest.raises(
        TypeError,
        match="Inheritance from multiple Actor base classes is not supported.",
    ):
        _ = factory[FakeActor]


async def test_base_actor_state_machine_is_created():
    factory = ActorStateMachineFactory()
    m = factory[Actor]
    assert m is factory[Actor]


async def test_state_machine_name_is_set():
    factory = ActorStateMachineFactory()

    assert factory[Actor].name == "Actor: "

    class FakeActor(Actor):
        ...

    assert factory[FakeActor].name == f"{FakeActor.__qualname__}: "
