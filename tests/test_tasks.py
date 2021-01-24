from functools import partial

import anyio
import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import TaskState
from jumpstarter.tasks import Success, task

pytestmark = pytest.mark.anyio


async def test_start_stop_tasks(subtests):
    class FakeActor(Actor):
        @task
        async def foo(self):
            raise Success()

    actor = FakeActor()

    async with anyio.create_task_group() as tg:
        start = partial(actor.start, task_group=tg)
        await tg.spawn(start)

        while True:
            await anyio.sleep(1)

    assert actor.state == f"starting↦foo↦{TaskState.running.name}"
