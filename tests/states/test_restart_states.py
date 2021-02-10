import pytest
from transitions import MachineError

from jumpstarter.states import (
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
def m():
    return Mock()


@pytest.fixture
async def actor_state_machine():
    state_machine = ActorStateMachine()
    state_machine._exit_stack = AsyncMock()
    return state_machine


@pytest.fixture
def state_machine(m, actor_state_machine):
    state_machine = ActorRestartStateMachine(actor_state_machine)
    state_machine.on_enter_restarting(m.restarting)
    state_machine.on_enter("restarting↦stopping", m.restarting_stopping)
    state_machine.on_enter("restarting↦starting", m.restarting_starting)
    state_machine.on_enter_restarted(m.restarted)

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
invalid_states_for_restart.remove(ActorRunningState.healthy)
invalid_states_for_restart.remove(ActorState.crashed)
# This list needs to be sorted for xdist to work.
invalid_states_for_restart = list(
    sorted(invalid_states_for_restart, key=lambda e: e.name)
)


@pytest.mark.parametrize("state", invalid_states_for_restart)
async def test_cant_restart_from_invalid_state(
    state, state_machine, actor_state_machine
):
    actor_state_machine.set_state(state)
    msg = "{}Can't trigger event restart from state {}!".format(
        state_machine.name,
        actor_state_machine._state,
    )
    with pytest.raises(MachineError, match=msg):
        await state_machine.restart()


@pytest.mark.parametrize("state", [ActorRunningState.healthy, ActorState.crashed])
@pytest.mark.timeout(4)
async def test_can_restart_twice(
    state, subtests, state_machine, actor_state_machine, m
):
    with subtests.test(f"can restart from {state} state"):
        actor_state_machine.set_state(state)
        await state_machine.restart()
        assert state_machine._restart_state == ActorRestartState.restarted
        m.assert_has_calls(
            [
                call.restarting(ANY),
                call.restarting_stopping(ANY),
                call.restarting_starting(ANY),
                call.restarted(ANY),
            ]
        )
    m.reset_mock()

    with subtests.test(f"can restart again after restarting once from {state} state"):
        await state_machine.restart()
        assert state_machine._restart_state == ActorRestartState.restarted
        m.assert_has_calls(
            [
                call.restarting(ANY),
                call.restarting_stopping(ANY),
                call.restarting_starting(ANY),
                call.restarted(ANY),
            ]
        )
    m.reset_mock()
