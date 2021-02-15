import pytest
from transitions import MachineError

from jumpstarter.states import (
    ActorRestartingState,
    ActorRestartState,
    ActorRestartStateMachine,
    ActorRunningState,
    ActorStartedState,
    ActorStartingState,
    ActorState,
    ActorStateMachine,
    ActorStoppingState,
)
from tests.mock import ANY, AsyncMock, Mock, call

pytestmark = pytest.mark.anyio


@pytest.fixture
def model():
    class Model:
        def __init__(self):
            self.m = Mock()
            del self.m.get_graph

            self._exit_stack = AsyncMock()

    return Model()


@pytest.fixture
async def actor_state_machine():
    return ActorStateMachine()


@pytest.fixture
def state_machine(model, actor_state_machine):
    state_machine = actor_state_machine._parallel_state_machines[0]
    actor_state_machine.add_model(model)

    state_machine.on_enter_restarting(model.m.restarting)
    state_machine.on_enter("restarting↦stopping", model.m.restarting_stopping)
    state_machine.on_enter("restarting↦starting", model.m.restarting_starting)
    state_machine.on_enter_restarted(model.m.restarted)

    return state_machine


async def test_initial_state_is_ignore(state_machine):
    assert state_machine._restart_state == ActorRestartState.ignore


invalid_states_for_restart = set(
    [state for state in ActorState]
    + [state for state in ActorStartingState]
    + [state for state in ActorStoppingState]
    + [state for state in ActorRunningState]
    + [state for state in ActorStartedState]
)
invalid_states_for_restart = invalid_states_for_restart - set(
    ActorRestartStateMachine.restart_allowed_from
)
# This list needs to be sorted for xdist to work.
invalid_states_for_restart = list(
    sorted(invalid_states_for_restart, key=lambda e: e.name)
)


@pytest.mark.parametrize("state", invalid_states_for_restart)
async def test_cant_restart_from_invalid_state(
    state, model, state_machine, actor_state_machine
):
    actor_state_machine.set_state(state)
    msg = "{}Can't trigger event restart from state {}!".format(
        state_machine.name,
        model._state,
    )
    with pytest.raises(MachineError, match=msg):
        await model.restart()


@pytest.mark.parametrize("state", ActorRestartStateMachine.restart_allowed_from)
@pytest.mark.timeout(4)
async def test_can_restart_twice(
    state, subtests, state_machine, actor_state_machine, model
):
    with subtests.test(f"can restart from {state} state"):
        actor_state_machine.set_state(state)
        await model.restart()
        assert model._restart_state == ActorRestartState.restarted
        model.m.assert_has_calls(
            [
                call.restarting(ANY),
                call.restarting_stopping(ANY),
                call.restarting_starting(ANY),
                call.restarted(ANY),
            ]
        )
    model.m.reset_mock()

    with subtests.test(f"can restart again after restarting once from {state} state"):
        await model.restart()
        assert model._restart_state == ActorRestartState.restarted
        model.m.assert_has_calls(
            [
                call.restarting(ANY),
                call.restarting_stopping(ANY),
                call.restarting_starting(ANY),
                call.restarted(ANY),
            ]
        )
    model.m.reset_mock()


@pytest.mark.parametrize("state", [state for state in ActorRestartState])
async def test_abort_restart(state, state_machine, model):
    state_machine.set_state(state)

    await model.abort_restart()
    assert model._restart_state == ActorRestartState.ignore


restart_states_excluding_ignore = [
    state for state in ActorRestartState if state != state.ignore
] + [state for state in ActorRestartingState]


@pytest.mark.parametrize("state", restart_states_excluding_ignore)
async def test_restart_during_crash(state, state_machine, actor_state_machine, model):
    class ExpectedException(Exception):
        ...

    getattr(
        model.m, "_".join(state_machine._get_enum_path(state))
    ).side_effect = ExpectedException
    actor_state_machine.set_state(ActorRunningState.healthy)

    with pytest.raises(ExpectedException):
        await model.restart()

    assert model._state == ActorState.crashed
    assert model._restart_state == ActorRestartState.ignore
