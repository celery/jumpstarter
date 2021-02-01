import typing
from functools import wraps

import anyio
from transitions.extensions.asyncio import NestedAsyncState, NestedAsyncTransition

from jumpstarter.states import ActorStartingState, TaskState, ActorState, ActorStateMachine

__all__ = ("task", "Success", "Failure", "Retry")


class TaskResult(Exception):
    pass


class Success(TaskResult):
    pass


class Failure(TaskResult):
    pass


class Retry(TaskResult):
    def __init__(self, countdown=None):
        self.countdown = countdown

        super().__init__()


def _get_task_state_name(name: str, state: TaskState):
    return f"{name}_task↦{state.name}"


class Task:
    def __init__(self, task_callback: typing.Callable):
        self._task_callback: typing.Callable = task_callback
        self.task_state: typing.Optional[NestedAsyncState] = None

        self.initialized_state: NestedAsyncState = NestedAsyncState(
            TaskState.initialized
        )
        self.running_state: NestedAsyncState = NestedAsyncState(TaskState.running)
        self.succeeded_state: NestedAsyncState = NestedAsyncState(TaskState.succeeded)
        self.failed_state: NestedAsyncState = NestedAsyncState(TaskState.failed)
        self.retrying_state: NestedAsyncState = NestedAsyncState(TaskState.retrying)
        self.crashed_state: NestedAsyncState = NestedAsyncState(TaskState.crashed)

        self.failed_state.add_substate(self.crashed_state)

    def __set_name__(self, owner, name):
        @wraps(self._task_callback)
        async def task_starter(event_data) -> None:
            self_ = event_data.model

            async def task_runner():
                retried = False

                while not self_._cancel_scope.cancel_called:
                    try:
                        await self._task_callback(self_)
                    except (Success, Failure):
                        # TODO: Change task state
                        return
                    except Retry as retry:
                        # TODO: Use a retry library
                        # TODO: Change task state
                        if retry.countdown:
                            await anyio.sleep(retry.countdown)

                        retried = True

                    if not retried:
                        # Yield so the scheduler may run another coroutine.
                        await anyio.sleep(0)
                    else:
                        # Retry occurred so next time we will yield to schedule the task more fairly.
                        retried = False

            await self_.spawn_task(task_runner, name)

        state_machine: ActorStateMachine = owner._state_machine
        transition: NestedAsyncTransition = state_machine.get_transitions(
            "start",
            ActorStartingState.resources_acquired,
            ActorStartingState.tasks_started,
        )[0]
        transition.before.append(task_starter)

        self._initialize_task_state(name, state_machine)

        state_machine.add_state(self.task_state)
        state_machine.initial.append(_get_task_state_name(name, TaskState.initialized))
        # state_machine.to(_get_task_state_name(name, TaskState.initialized))

        setattr(owner, f"__{name}", self._task_callback)
        setattr(owner, name, self)

    def _initialize_task_state(self, name, state_machine):
        self.task_state = NestedAsyncState(f"{name}_task")
        self.task_state.add_substates(
            (
                self.initialized_state,
                self.running_state,
                self.succeeded_state,
                self.failed_state,
                self.retrying_state,
                self.crashed_state,
            )
        )
        self.task_state.initial = _get_task_state_name(name, TaskState.initialized)

        transition = state_machine.get_transitions(
            "start",
            state_machine.actor_state.starting.value.tasks_started,
            state_machine.actor_state.started,
        )[0]
        transition.after.append(f"run_{name}")

        state_machine.add_transition(
            f"run_{name}",
            state_machine.actor_state.started,
            _get_task_state_name(name, TaskState.initialized),
            after=[f"run_{name}"],
        )

        state_machine.add_transition(
            f"run_{name}",
            _get_task_state_name(name, TaskState.initialized),
            _get_task_state_name(name, TaskState.running),
        )

        state_machine.add_transition(
            f"{name}_done",
            _get_task_state_name(name, TaskState.running),
            _get_task_state_name(name, TaskState.succeeded),
        )

        state_machine.add_transition(
            f"{name}_failed",
            _get_task_state_name(name, TaskState.running),
            _get_task_state_name(name, TaskState.failed),
        )

        state_machine.add_transition(
            f"{name}_crashed",
            _get_task_state_name(name, TaskState.failed),
            _get_task_state_name(name, TaskState.crashed),
        )

        state_machine.add_transition(
            f"retry_{name}",
            _get_task_state_name(name, TaskState.running),
            _get_task_state_name(name, TaskState.retrying),
        )

        state_machine.add_transition(
            f"restart_{name}",
            _get_task_state_name(name, TaskState.retrying),
            _get_task_state_name(name, TaskState.running),
        )

        state_machine.add_transition(
            f"restart_{name}",
            _get_task_state_name(name, TaskState.failed),
            _get_task_state_name(name, TaskState.running),
        )

        state_machine.add_transition(
            f"restart_{name}",
            _get_task_state_name(name, TaskState.crashed),
            _get_task_state_name(name, TaskState.running),
        )

        state_machine.add_transition(
            f"restart_{name}",
            _get_task_state_name(name, TaskState.succeeded),
            _get_task_state_name(name, TaskState.running),
        )

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")

    def __aenter__(self):
        pass

    def __aexit__(self, *exc_info):
        if exc_info:
            # TODO: Change state to crashed
            pass


def task(task_callback: typing.Callable) -> Task:
    return Task(task_callback)
