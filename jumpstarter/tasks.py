import typing

__all__ = ("task",)

from functools import wraps

import anyio

from jumpstarter.states import ActorStartingState


class Task:
    def __init__(self, task_callback: typing.Callable):
        self._task_callback: typing.Callable = task_callback

    def __set_name__(self, owner, name):
        @wraps(self._task_callback)
        async def task_starter(event_data) -> None:
            self_ = event_data.model

            async def task_runner():
                while not self_._cancel_scope.cancelled:
                    await self._task_callback(self_)

                    # Yield so the scheduler may run another coroutine.
                    await anyio.sleep(0)

            await self_.spawn_task(task_runner)

        transition = owner._state_machine.get_transitions(
            "start",
            ActorStartingState.resources_acquired,
            ActorStartingState.tasks_started,
        )[0]
        transition.before.append(task_starter)

        setattr(owner, f"__{name}", self._task_callback)
        setattr(owner, name, self)

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")


def task(task_callback: typing.Callable) -> Task:
    return Task(task_callback)
