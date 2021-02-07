import pytest

from jumpstarter.states import ActorRestartState, ActorRestartStateMachine, ActorStateMachine, ActorRunningState, \
    ActorState
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


async def test_can_restart_twice(state_machine, actor_state_machine, m):
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
