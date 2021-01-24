import pytest

from jumpstarter.states import ActorStateMachine
from tests.mock import ANY, AsyncMock, Mock, call

pytestmark = pytest.mark.anyio


async def test_start(subtests):
    m = Mock()

    state_machine = ActorStateMachine()
    state_machine._exit_stack = AsyncMock()

    state_machine.on_exit_initializing(m.initializing_mock)
    state_machine.on_enter_initialized(m.initialized_mock)
    state_machine.on_enter_starting(m.starting_mock)
    state_machine.on_enter("starting↦dependencies_started", m.dependencies_started_mock)
    state_machine.on_enter("starting↦resources_acquired", m.resources_acquired_mock)
    state_machine.on_enter("starting↦tasks_started", m.tasks_started_mock)
    state_machine.on_enter_started(m.started_mock)
    state_machine.on_enter_stopping(m.stopping_mock)
    state_machine.on_enter("stopping↦tasks_stopped", m.tasks_stopped_mock)
    state_machine.on_enter("stopping↦resources_released", m.resources_released_mock)
    state_machine.on_enter("stopping↦dependencies_stopped", m.dependencies_stopped_mock)
    state_machine.on_enter_stopped(m.stopped_mock)
    state_machine.on_enter_crashed(m.crashed_mock)

    await state_machine.start()

    with subtests.test("actor state is started"):
        assert state_machine.is_started(), state_machine.state

    with subtests.test("states are transitioned in order"):
        m.assert_has_calls(
            [
                call.initializing_mock(ANY),
                call.initialized_mock(ANY),
                call.starting_mock(ANY),
                call.dependencies_started_mock(ANY),
                call.resources_acquired_mock(ANY),
                call.tasks_started_mock(ANY),
                call.started_mock(ANY),
            ]
        )

    with subtests.test("no invalid transitions occurred"):
        m.stopping_mock.assert_not_called()
        m.stopped_mock.assert_not_called()
        m.crashed_mock.assert_not_called()
        m.tasks_stopped_mock.assert_not_called()
        m.resources_released_mock.assert_not_called()
        m.dependencies_stopped_mock.assert_not_called()


async def test_stop(subtests):
    m = Mock()

    state_machine = ActorStateMachine()
    state_machine._exit_stack = AsyncMock()
    state_machine.set_state("started")

    state_machine.on_exit_initializing(m.initializing_mock)
    state_machine.on_enter_initialized(m.initialized_mock)
    state_machine.on_enter_starting(m.starting_mock)
    state_machine.on_enter("starting↦dependencies_started", m.dependencies_started_mock)
    state_machine.on_enter("starting↦resources_acquired", m.resources_acquired_mock)
    state_machine.on_enter("starting↦tasks_started", m.tasks_started_mock)
    state_machine.on_enter_started(m.started_mock)
    state_machine.on_enter_stopping(m.stopping_mock)
    state_machine.on_enter("stopping↦tasks_stopped", m.tasks_stopped_mock)
    state_machine.on_enter("stopping↦resources_released", m.resources_released_mock)
    state_machine.on_enter("stopping↦dependencies_stopped", m.dependencies_stopped_mock)
    state_machine.on_enter_stopped(m.stopped_mock)
    state_machine.on_enter_crashed(m.crashed_mock)

    await state_machine.stop()

    with subtests.test("actor state is started"):
        assert state_machine.is_stopped(), state_machine.state

    with subtests.test("states are transitioned in order"):
        m.assert_has_calls(
            [
                call.stopping_mock(ANY),
                call.tasks_stopped_mock(ANY),
                call.resources_released_mock(ANY),
                call.dependencies_stopped_mock(ANY),
                call.stopped_mock(ANY),
            ]
        )

    with subtests.test("no invalid transitions occurred"):
        m.initializing_mock.assert_not_called()
        m.initialized_mock.assert_not_called()
        m.starting_mock.assert_not_called()
        m.dependencies_started_mock.assert_not_called()
        m.resources_acquired_mock.assert_not_called()
        m.tasks_started_mock.assert_not_called()
        m.started_mock.assert_not_called()
