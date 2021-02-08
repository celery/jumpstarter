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
from tests.mock import ANY, Mock, call

pytestmark = pytest.mark.anyio


@pytest.fixture
def m():
    return Mock()


@pytest.fixture
def actor_state_machine():
    return ActorStateMachine()


@pytest.fixture
def state_machine(m, actor_state_machine):
    state_machine = ActorRestartStateMachine(actor_state_machine)
    state_machine.on_enter_restarting(m.restarting)
    state_machine.on_enter_restarted(m.restarted)

    return state_machine


def test_initial_state_is_ignore(state_machine):
    assert state_machine._state == ActorRestartState.ignore


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


async def test_can_restart_twice(subtests, state_machine, actor_state_machine, m):
    actor_state_machine.set_state(ActorRunningState.healthy)
    await state_machine.restart()
    assert state_machine._state == ActorRestartState.restarted
    m.assert_has_calls([call.restarting(ANY), call.restarted(ANY)])
    m.reset_mock()

    await state_machine.restart()
    assert state_machine._state == ActorRestartState.restarted
    m.assert_has_calls([call.restarting(ANY), call.restarted(ANY)])
    m.reset_mock()

    actor_state_machine.set_state(ActorState.crashed)
    await state_machine.restart()
    assert state_machine._state == ActorRestartState.restarted
    m.assert_has_calls([call.restarting(ANY), call.restarted(ANY)])
    m.reset_mock()

    await state_machine.restart()
    assert state_machine._state == ActorRestartState.restarted
    m.assert_has_calls([call.restarting(ANY), call.restarted(ANY)])
