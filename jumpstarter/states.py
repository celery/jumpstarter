from enum import Enum, auto

from transitions_anyio import HierarchicalAnyIOMachine


class ActorStartingState(Enum):
    dependencies_started = auto()
    resources_acquired = auto()
    tasks_started = auto()


class ActorStoppingState(Enum):
    tasks_stopped = auto()
    resources_released = auto()
    dependencies_stopped = auto()


class ActorState(Enum):
    initializing = auto()
    initialized = auto()
    # restarting = ActorRestartState
    starting = ActorStartingState
    started = auto()
    stopping = ActorStoppingState
    stopped = auto()
    crashed = auto()


class ActorStateMachine(HierarchicalAnyIOMachine):
    def __init__(self, actor_state=ActorState):
        super().__init__(
            states=actor_state,
            initial=actor_state.initializing,
            auto_transitions=False,
            send_event=True,
        )

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

        transition = self.get_transitions(
            "stop",
            actor_state.stopping.value.tasks_stopped,
            actor_state.stopping.value.resources_released,
        )[0]
        transition.before.append(_release_resources)


async def _release_resources(event_data):
    await event_data.model._exit_stack.aclose()
