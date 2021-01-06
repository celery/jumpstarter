from unittest.mock import AsyncMock, Mock, call

import anyio
import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import ActorState
from jumpstarter.resources import NotAResourceError, Resource


@pytest.mark.anyio
@pytest.mark.skip
async def test_start(subtests):
    m = Mock()

    a = Actor()

    a.on_exit_initializing(m.initializing_mock)
    a.on_enter_initialized(m.initialized_mock)
    a.on_enter_starting(m.starting_mock)
    a.on_enter("starting↦dependencies_started", m.dependencies_started_mock)
    a.on_enter("starting↦resources_acquired", m.resources_acquired_mock)
    a.on_enter("starting↦tasks_started", m.tasks_started_mock)
    a.on_enter_started(m.started_mock)
    a.on_enter_stopping(m.stopping_mock)
    a.on_enter("stopping↦tasks_stopped", m.tasks_stopped_mock)
    a.on_enter("stopping↦resources_released", m.resources_released_mock)
    a.on_enter("stopping↦dependencies_stopped", m.dependencies_stopped_mock)
    a.on_enter_stopped(m.stopped_mock)
    a.on_enter_crashed(m.crashed_mock)

    await a.start()

    with subtests.test("actor state is started"):
        assert a.is_started(), a.state

    with subtests.test("states are transitioned in order"):
        m.assert_has_calls(
            [
                call.initializing_mock(),
                call.initialized_mock(),
                call.starting_mock(),
                call.dependencies_started_mock(),
                call.resources_acquired_mock(),
                call.tasks_started_mock(),
                call.started_mock(),
            ]
        )

    with subtests.test("no invalid transitions occurred"):
        m.stopping_mock.assert_not_called()
        m.stopped_mock.assert_not_called()
        m.crashed_mock.assert_not_called()
        m.tasks_stopped_mock.assert_not_called()
        m.resources_released_mock.assert_not_called()
        m.dependencies_stopped_mock.assert_not_called()


@pytest.mark.anyio
@pytest.mark.skip
async def test_stop(subtests):
    m = Mock()

    a = Actor()
    a.set_state("started")

    a.on_exit_initializing(m.initializing_mock)
    a.on_enter_initialized(m.initialized_mock)
    a.on_enter_starting(m.starting_mock)
    a.on_enter("starting↦dependencies_started", m.dependencies_started_mock)
    a.on_enter("starting↦resources_acquired", m.resources_acquired_mock)
    a.on_enter("starting↦tasks_started", m.tasks_started_mock)
    a.on_enter_started(m.started_mock)
    a.on_enter_stopping(m.stopping_mock)
    a.on_enter("stopping↦tasks_stopped", m.tasks_stopped_mock)
    a.on_enter("stopping↦resources_released", m.resources_released_mock)
    a.on_enter("stopping↦dependencies_stopped", m.dependencies_stopped_mock)
    a.on_enter_stopped(m.stopped_mock)
    a.on_enter_crashed(m.crashed_mock)

    await a.stop()

    with subtests.test("actor state is started"):
        assert a.is_stopped(), a.state

    with subtests.test("states are transitioned in order"):
        m.assert_has_calls(
            [
                call.stopping_mock(),
                call.tasks_stopped_mock(),
                call.resources_released_mock(),
                call.dependencies_stopped_mock(),
                call.stopped_mock(),
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


@pytest.mark.anyio
async def test_acquire_resource(subtests):
    m = AsyncMock()

    class FakeActor(Actor):
        @Actor.acquire_resource
        def resource(self):
            return m

    a = FakeActor()

    assert a.state == ActorState.initializing

    async with anyio.create_task_group() as tg:
        await a.start(tg)

    assert a.state == ActorState.started

    with subtests.test("__aenter__ is called"):
        m.__aenter__.assert_called_once_with(m)
        m.__aexit__.assert_not_called()

    assert a.state != ActorState.stopped
    await a.stop()

    with subtests.test("__aexit__ is called"):
        m.__aexit__.assert_called_once_with(m, None, None, None)


@pytest.mark.anyio
async def test_acquire_resource_not_a_resource(subtests):
    m = AsyncMock()

    del m.__aenter__

    i = 0

    class FakeActor(Actor):
        @Resource
        def resource(self):
            nonlocal i
            i += 1
            return m

    a = FakeActor()

    with pytest.raises(
            NotAResourceError,
            match=r"The return value of resource is not a context manager.\n"
                  r"Instead we got <AsyncMock id='[0-9]+'>",
    ):
        await a.start()
