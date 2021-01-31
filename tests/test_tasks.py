from functools import partial

import anyio
import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import TaskState, ActorState
from jumpstarter.tasks import Success, task

pytestmark = pytest.mark.anyio


async def test_start_stop_tasks(subtests):
    called = False

    class FakeActor(Actor):
        @task
        async def foo(self):
            nonlocal called
            called = True
            raise Success()

    actor = FakeActor()

    with subtests.test("task state is set to running"):
        state = [actor.state] if not isinstance(actor.state, list) else actor.state
        assert TaskState.initialized in state and ActorState.initializing in state

    transition = FakeActor._state_machine.get_transitions(f"run_foo")[0]

    async with anyio.create_task_group() as tg:
        await actor.start(task_group=tg)

    with subtests.test("task foo called and exited without error"):
        assert called

    with subtests.test("task state is set to running"):
        state = [actor.state] if not isinstance(actor.state, list) else actor.state
        assert TaskState.running in state and ActorState.started in state
