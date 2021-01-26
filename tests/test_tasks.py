from functools import partial

import anyio
import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import TaskState
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

    async with anyio.create_task_group() as tg:
        await actor.start(task_group=tg)

    assert called
