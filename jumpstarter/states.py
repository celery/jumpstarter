from enum import Enum, auto

import anyio
import transitions
from anyio.abc import TaskGroup
from transitions.extensions.nesting import NestedState

try:
    import pygraphviz  # noqa: F401
except ImportError:
    from transitions_anyio import HierarchicalAnyIOMachine as BaseStateMachine
else:
    from transitions_anyio import HierarchicalAnyIOGraphMachine as BaseStateMachine

NestedState.separator = "↦"


class ActorStartingState(Enum):
    dependencies_started = auto()
    resources_acquired = auto()
    tasks_started = auto()


class ActorStoppingState(Enum):
    tasks_stopped = auto()
    resources_released = auto()
    dependencies_stopped = auto()


class ActorStartedState(Enum):
    healthy = auto()


class ActorState(Enum):
    initializing = auto()
    initialized = auto()
    # restarting = ActorRestartState
    starting = ActorStartingState
    started = ActorStartedState
    stopping = ActorStoppingState
    stopped = auto()
    crashed = auto()


class ActorStateMachine(BaseStateMachine):
    def __init__(self, actor_state=ActorState):
        super().__init__(
            states=actor_state,
            initial=actor_state.initializing,
            auto_transitions=False,
            send_event=True,
        )

        started_state = self.get_state(ActorState.started)
        started_state.initial = [ActorStartedState.healthy]

        self.add_ordered_transitions(
            states=[
                actor_state.initializing,
                actor_state.initialized,
                actor_state.starting,
                actor_state.starting.value.dependencies_started,
                actor_state.starting.value.resources_acquired,
                actor_state.starting.value.tasks_started,
            ],
            trigger="start",
            loop=False,
            after="start",
        )

        self.add_transition(
            "start", actor_state.starting.value.tasks_started, actor_state.started
        )

        self.add_ordered_transitions(
            states=[
                actor_state.started,
                actor_state.stopping,
                actor_state.stopping.value.tasks_stopped,
                actor_state.stopping.value.resources_released,
                actor_state.stopping.value.dependencies_stopped,
            ],
            trigger="stop",
            loop=False,
            after="stop",
        )

        self.add_transition(
            "stop", actor_state.stopping.value.dependencies_stopped, actor_state.stopped
        )

        self.add_transition("report_error", "*", actor_state.crashed)
        self.add_transition(
            "start", actor_state.stopped, actor_state.starting, after="start"
        )

        transition = self.get_transitions(
            "stop",
            actor_state.stopping.value.tasks_stopped,
            actor_state.stopping.value.resources_released,
        )[0]
        transition.before.append(_release_resources)

        self.on_enter(actor_state.starting, _maybe_acquire_task_group)


async def _release_resources(event_data: transitions.EventData) -> None:
    await event_data.model._exit_stack.aclose()


async def _maybe_acquire_task_group(event_data) -> None:
    self_ = event_data.model

    try:
        task_group: TaskGroup = event_data.kwargs["task_group"]
    except KeyError:
        # TODO: Log in case we're creating our own task group
        task_group: TaskGroup = anyio.create_task_group()
        await self_._exit_stack.enter_async_context(task_group)

    self_._task_group = task_group
