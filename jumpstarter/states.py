from enum import Enum, auto

import transitions
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


class ActorRunningState(Enum):
    healthy = auto()
    degraded = auto()
    unhealthy = auto()


class ActorStartedState(Enum):
    running = ActorRunningState
    paused = auto()


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

        started_state = self.get_state(actor_state.started)
        started_state.initial = actor_state.started.value.running
        running_state = self.get_state(actor_state.started.value.running)
        running_state.initial = actor_state.started.value.running.value.healthy

        self._create_bootup_transitions(actor_state)
        self._create_shutdown_transitions(actor_state)
        self._create_restart_transitions(actor_state)
        self.add_transition("report_error", "*", actor_state.crashed)
        self._create_started_substates_transitions(actor_state)

        transition = self.get_transitions(
            "stop",
            actor_state.stopping.value.tasks_stopped,
            actor_state.stopping.value.resources_released,
        )[0]
        transition.before.append(_release_resources)

    def _create_started_substates_transitions(self, actor_state):
        self.add_transition(
            "pause", actor_state.started.value.running, actor_state.started.value.paused
        )
        self.add_transition(
            "resume",
            actor_state.started.value.paused,
            actor_state.started.value.running,
        )

        self.add_transition(
            "recover",
            [
                actor_state.started.value.running.value.degraded,
                actor_state.started.value.running.value.unhealthy,
            ],
            actor_state.started.value.running.value.healthy,
        )
        self.add_transition(
            "report_warning",
            [
                actor_state.started.value.running.value.healthy,
                actor_state.started.value.running.value.unhealthy,
            ],
            actor_state.started.value.running.value.degraded,
        )
        self.add_transition(
            "report_problem",
            [
                actor_state.started.value.running.value.degraded,
                actor_state.started.value.running.value.healthy,
            ],
            actor_state.started.value.running.value.unhealthy,
        )

    def _create_restart_transitions(self, actor_state):
        self.add_transition(
            "start", actor_state.stopped, actor_state.starting, after="start"
        )

    def _create_shutdown_transitions(self, actor_state):
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

    def _create_bootup_transitions(self, actor_state):
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


async def _release_resources(event_data: transitions.EventData) -> None:
    await event_data.model._exit_stack.aclose()
