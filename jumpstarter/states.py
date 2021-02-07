from __future__ import annotations

import typing
from enum import Enum, auto

import transitions
from transitions import EventData
from transitions.core import _LOGGER
from transitions.extensions.asyncio import NestedAsyncTransition
from transitions.extensions.nesting import NestedState

try:
    import pygraphviz  # noqa: F401
except ImportError:
    from transitions_anyio import HierarchicalAnyIOMachine as BaseStateMachine
else:
    from transitions_anyio import HierarchicalAnyIOGraphMachine as BaseStateMachine

NestedState.separator = "↦"


class ChildStateEnum(dict):
    def __init__(self, children, initial):
        super(ChildStateEnum, self).__init__(children=children, initial=initial)

    def __getattr__(self, item):
        try:
            return super().__getattr__(item)
        except AttributeError:
            return getattr(self["children"], item)


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
    running = ChildStateEnum(
        children=ActorRunningState, initial=ActorRunningState.healthy
    )
    paused = auto()


class ActorRestartingState(Enum):
    starting = auto()
    stopping = auto()


class ActorRestartState(Enum):
    ignore = auto()
    restarting = ChildStateEnum(
        children=ActorRestartingState, initial=ActorRestartingState.starting
    )
    restarted = auto()


class ActorState(Enum):
    initializing = auto()
    initialized = auto()
    starting = ActorStartingState
    started = ChildStateEnum(
        children=ActorStartedState, initial=ActorStartedState.running
    )
    stopping = ActorStoppingState
    stopped = auto()
    crashed = auto()


class AsyncTransitionWithLogging(NestedAsyncTransition):
    async def execute(self, event_data: EventData) -> bool:
        _LOGGER.debug("%sBefore callbacks:%s", event_data.machine.name, self.before)
        _LOGGER.debug("%sAfter callbacks:%s", event_data.machine.name, self.after)

        return await super().execute(event_data)


class ActorRestartStateMachine(BaseStateMachine):
    def __init__(
        self,
        actor_state_machine: ActorStateMachine,
        restart_state: ActorRestartState = ActorRestartState,
    ):
        super(ActorRestartStateMachine, self).__init__(
            states=restart_state,
            initial=restart_state.ignore,
            model_attribute="_state",
            auto_transitions=False,
            send_event=True,
        )

        self.actor_state_machine: ActorStateMachine = actor_state_machine
        self.add_transition(
            "restart",
            restart_state.ignore,
            restart_state.restarting,
            after="restart",
            conditions=[self._check_if_running_or_crashed],
        )
        self.add_transition(
            "restart",
            restart_state.restarting.value.starting,
            restart_state.restarting.value.stopping,
            after="restart",
        )
        self.add_transition(
            "restart", restart_state.restarting.value.stopping, restart_state.restarted
        )

        self.add_transition(
            "restart",
            restart_state.restarted,
            restart_state.restarting,
            after="restart",
            conditions=[self._check_if_running_or_crashed]
        )

    def _check_if_running_or_crashed(self, event_data: EventData) -> bool:
        return (
            self.actor_state_machine._state == ActorState.crashed
            or self.actor_state_machine._state
            == ActorState.started.value.running.value.healthy
        )


class ActorStateMachine(BaseStateMachine):
    transition_cls = AsyncTransitionWithLogging

    # region Dunder methods

    def __init__(
        self,
        actor_state: ActorState | ActorStateMachine = ActorState,
        name: typing.Optional[str] = None,
        inherited: bool = False,
    ):
        if inherited:
            base_actor_state_machine = actor_state
            super().__init__(
                states=base_actor_state_machine,
                initial=base_actor_state_machine.initial,
                auto_transitions=False,
                send_event=True,
                name=name,
                model_attribute="_state",
            )
        else:
            super().__init__(
                states=actor_state,
                initial=actor_state.initializing,
                auto_transitions=False,
                send_event=True,
                name=name,
                model_attribute="_state",
            )

            self._create_bootup_transitions(actor_state)
            self._create_shutdown_transitions(actor_state)
            self._create_restart_transitions(actor_state)
            self._create_crashed_transitions(actor_state)
            self._create_started_substates_transitions(actor_state)

        self._parallel_state_machines: typing.List[BaseStateMachine] = []

    # endregion

    # region Public API

    def register_parallel_state_machine(self, machine: BaseStateMachine) -> None:
        self._parallel_state_machines.append(machine)

    # endregion

    # region Protected API

    def _create_crashed_transitions(self, actor_state):
        self.add_transition("report_error", "*", actor_state.crashed)
        self.add_transition("start", actor_state.crashed, actor_state.starting)

    def _create_started_substates_transitions(self, actor_state):
        self.add_transition(
            "pause", actor_state.started.value.running, actor_state.started.value.paused
        )
        self.add_transition(
            "resume",
            actor_state.started.value.paused,
            actor_state.started.value.running.value.healthy,
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

        transition = self.get_transitions(
            "stop",
            actor_state.stopping.value.tasks_stopped,
            actor_state.stopping.value.resources_released,
        )[0]
        transition.before.append(_release_resources)

    def _create_bootup_transitions(self, actor_state):
        self.add_transition(
            "initialize", actor_state.initializing, actor_state.initialized
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
            "start",
            actor_state.starting.value.tasks_started,
            actor_state.started,
        )

    # endregion


async def _release_resources(event_data: transitions.EventData) -> None:
    await event_data.model._exit_stack.aclose()
