from enum import Enum, auto

import transitions
from transitions.extensions.nesting import NestedState
from transitions_anyio import HierarchicalAnyIOMachine, HierarchicalAnyIOGraphMachine

NestedState.separator = "↦"


class ActorStartingState(Enum):
    dependencies_started = auto()
    resources_acquired = auto()
    tasks_started = auto()


class ActorStoppingState(Enum):
    tasks_stopped = auto()
    resources_released = auto()
    dependencies_stopped = auto()


class ActorRestartingState(Enum):
    starting = auto()
    stopping = auto()


class ActorState(Enum):
    initializing = auto()
    initialized = auto()
    starting = ActorStartingState
    started = auto()
    stopping = ActorStoppingState
    stopped = auto()
    restarting = ActorRestartingState
    crashed = auto()


class ActorStateTriggers(str, Enum):
    def _generate_next_value_(name, *args):
        return name.lower()

    init = auto()
    start = auto()
    stop = auto()
    restart = auto()
    report_error = auto()


class ActorStateMachine(HierarchicalAnyIOGraphMachine):
    def __init__(self, actor_state=ActorState):
        super().__init__(
            states=actor_state,
            initial=actor_state.initializing,
            auto_transitions=False,
            send_event=True,
        )

        # TODO: Does transitions have an API for Enum based parallel?
        self.add_states(
            [
                {
                    "name": actor_state.restarting.name,
                    "parallel": [
                        actor_state.starting.name,
                        actor_state.stopping.name,
                    ],
                }
            ]
        )

        self.add_transition(
            ActorStateTriggers.init,
            actor_state.initializing,
            actor_state.initialized,
        )

        self.add_ordered_transitions(
            states=[
                actor_state.initialized,
                actor_state.starting,
                actor_state.starting.value.dependencies_started,
                actor_state.starting.value.resources_acquired,
                actor_state.starting.value.tasks_started,
            ],
            trigger=ActorStateTriggers.start,
            loop=False,
            after=ActorStateTriggers.start,
        )

        self.add_transition(
            ActorStateTriggers.start,
            actor_state.starting.value.tasks_started,
            actor_state.started,
        )

        self.add_ordered_transitions(
            states=[
                actor_state.started,
                actor_state.stopping,
                actor_state.stopping.value.tasks_stopped,
                actor_state.stopping.value.resources_released,
                actor_state.stopping.value.dependencies_stopped,
            ],
            trigger=ActorStateTriggers.stop,
            loop=False,
            after=ActorStateTriggers.stop,
        )

        self.add_transition(
            ActorStateTriggers.stop,
            actor_state.stopping.value.dependencies_stopped,
            actor_state.stopped,
        )

        self.add_transition("report_error", "*", actor_state.crashed)
        self.add_transition(
            ActorStateTriggers.start, actor_state.stopped, actor_state.starting
        )

        self.add_transition(
            ActorStateTriggers.restart,
            actor_state.started,
            actor_state.restarting,
            after=ActorStateTriggers.stop,
        )
        self.add_transition(
            ActorStateTriggers.stop,
            actor_state.restarting.stopping,
            actor_state.stopping,
            after=ActorStateTriggers.stop,
        )

        transition = self.get_transitions(
            ActorStateTriggers.stop,
            actor_state.stopping.value.tasks_stopped,
            actor_state.stopping.value.resources_released,
        )[0]
        transition.before.append(_release_resources)


async def _release_resources(event_data: transitions.EventData) -> None:
    await event_data.model._exit_stack.aclose()
