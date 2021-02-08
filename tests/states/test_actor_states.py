import pytest

from jumpstarter.states import (
    ActorRunningState,
    ActorStateMachine,
    HierarchicalParallelAnyIOGraphMachine, diagrams,
)
from tests.mock import ANY, AsyncMock, Mock, call

pytestmark = pytest.mark.anyio


@pytest.fixture
def m():
    return Mock()


@pytest.fixture
def state_machine(m):
    state_machine = ActorStateMachine()
    state_machine._exit_stack = AsyncMock()

    state_machine.on_exit_initializing(m.initializing_mock)
    state_machine.on_enter_initialized(m.initialized_mock)
    state_machine.on_enter_starting(m.starting_mock)
    state_machine.on_enter("starting↦dependencies_started", m.dependencies_started_mock)
    state_machine.on_enter("starting↦resources_acquired", m.resources_acquired_mock)
    state_machine.on_enter("starting↦tasks_started", m.tasks_started_mock)
    state_machine.on_enter_started(m.started_mock)
    state_machine.on_enter("started↦running", m.started_running_mock)
    state_machine.on_enter("started↦running↦healthy", m.started_running_healthy_mock)
    state_machine.on_enter_stopping(m.stopping_mock)
    state_machine.on_enter("stopping↦tasks_stopped", m.tasks_stopped_mock)
    state_machine.on_enter("stopping↦resources_released", m.resources_released_mock)
    state_machine.on_enter("stopping↦dependencies_stopped", m.dependencies_stopped_mock)
    state_machine.on_enter_stopped(m.stopped_mock)
    state_machine.on_enter_crashed(m.crashed_mock)

    return state_machine


async def test_start(subtests, state_machine, m):
    await state_machine.start()

    with subtests.test("actor state is started->running->healthy"):
        assert state_machine._state == ActorRunningState.healthy

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
                call.started_running_mock(ANY),
                call.started_running_healthy_mock(ANY),
            ]
        )

    with subtests.test("no invalid transitions occurred"):
        m.stopping_mock.assert_not_called()
        m.stopped_mock.assert_not_called()
        m.crashed_mock.assert_not_called()
        m.tasks_stopped_mock.assert_not_called()
        m.resources_released_mock.assert_not_called()
        m.dependencies_stopped_mock.assert_not_called()


async def test_stop(subtests, state_machine, m):
    state_machine.set_state("started↦running↦healthy")
    await state_machine.stop()

    with subtests.test("actor state is stopped"):
        assert state_machine.is_stopped(), state_machine._state

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


async def test_stop_paused(subtests, state_machine, m):
    state_machine.set_state("started↦running↦healthy")
    await state_machine.pause()
    await state_machine.stop()

    with subtests.test("actor state is stopped"):
        assert state_machine.is_stopped(), state_machine._state

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


def test_add_model_adds_the_model_to_all_parallel_state_machines(state_machine):
    fake_state_machine = HierarchicalParallelAnyIOGraphMachine(name="Fake")
    state_machine.register_parallel_state_machine(fake_state_machine)

    class Model:
        ...

    model = Model()
    state_machine.add_model(model)

    assert state_machine.models[1] == fake_state_machine.models[1] == model

    if diagrams:
        assert hasattr(model, "get_fake_graph")
