from __future__ import annotations

from enum import Enum, auto
from functools import partial
from typing import TYPE_CHECKING, Any

import anyio
from anyio.abc import Event
from transitions import EventData
from transitions.core import _LOGGER, MachineError, listify
from transitions.extensions import GraphMachine
from transitions.extensions.asyncio import NestedAsyncTransition
from transitions.extensions.nesting import NestedState

if TYPE_CHECKING:
    from jumpstarter.actors import Actor
else:
    Actor = None

try:
    import pygraphviz  # noqa: F401
except ImportError:
    from transitions_anyio import HierarchicalAnyIOMachine
    from transitions_anyio import HierarchicalAnyIOMachine as BaseStateMachine

    diagrams = False
else:
    from transitions_anyio import HierarchicalAnyIOGraphMachine as BaseStateMachine
    from transitions_anyio import HierarchicalAnyIOMachine

    diagrams = True

NestedState.separator = "↦"


# region Enums


class ChildStateEnum(dict):
    def __init__(self, children, initial):
        super().__init__(children=children, initial=initial)

    def __getattr__(
        self, item: str
    ) -> ActorRunningState | ActorStartedState | ActorRestartingState:
        try:
            return super().__getattr__(item)
        except AttributeError:
            return getattr(self["children"], item)


# region States


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
    stopping = auto()
    starting = auto()


class ActorRestartState(Enum):
    ignore = auto()
    restarting = ChildStateEnum(
        children=ActorRestartingState, initial=ActorRestartingState.stopping
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


# endregion

# endregion

# State Machine Customization


class AsyncTransitionWithLogging(NestedAsyncTransition):
    async def execute(self, event_data: EventData) -> bool:
        _LOGGER.debug("%sBefore callbacks:%s", event_data.machine.name, self.before)
        _LOGGER.debug("%sAfter callbacks:%s", event_data.machine.name, self.after)

        return await super().execute(event_data)


if diagrams:

    class ParallelGraphMachine(GraphMachine):
        def add_model(self, model: str | Actor, initial: None = None) -> None:
            models = listify(model)
            super(GraphMachine, self).add_model(models, initial)
            for mod in models:
                mod = self if mod == "self" else mod
                get_graph_method_name = "get_graph"
                if hasattr(mod, get_graph_method_name):
                    if not self.name:
                        raise AttributeError(
                            "Model already has a get_graph attribute and state machine name was not specified. "
                            "Graph retrieval cannot be bound."
                        )
                    get_graph_method_name = f"get_{self.name[:-2].lower()}_graph"
                setattr(mod, get_graph_method_name, partial(self._get_graph, mod))
                _ = getattr(mod, get_graph_method_name)(
                    title=self.title, force_new=True
                )  # initialises graph

    class HierarchicalParallelAnyIOGraphMachine(
        ParallelGraphMachine, HierarchicalAnyIOMachine
    ):
        transition_cls = NestedAsyncTransition


else:
    HierarchicalParallelAnyIOGraphMachine = BaseStateMachine


# endregion

# region State Machines


class ActorRestartStateMachine(HierarchicalParallelAnyIOGraphMachine):
    restart_allowed_from = (
        ActorState.crashed,
        ActorState.started.value.running.value.healthy,
        ActorState.started.value.running.value.degraded,
        ActorState.started.value.running.value.unhealthy,
        ActorState.started.value.paused,
    )

    def __init__(
        self,
        restart_state: ActorRestartState = ActorRestartState,
    ):
        super().__init__(
            states=restart_state,
            initial=restart_state.ignore,
            model_attribute="_restart_state",
            auto_transitions=False,
            send_event=True,
            queued=True,
            name="Restart",
            finalize_event=_crash_if_an_error_occurred,
        )

        self.add_transition(
            "restart",
            restart_state.ignore,
            restart_state.restarting,
            after="restart",
            conditions=self._can_restart,
        )
        self.add_transition(
            "restart",
            restart_state.restarting.value.stopping,
            restart_state.restarting.value.starting,
            after="restart",
        )
        self.add_transition(
            "restart", restart_state.restarting.value.starting, restart_state.restarted
        )

        self.add_transition(
            "restart",
            restart_state.restarted,
            restart_state.restarting,
            after="restart",
            conditions=self._can_restart,
        )

        self.add_transition("abort_restart", "*", restart_state.ignore)

        self.on_enter("restarting↦stopping", self._stop_and_wait_for_completion)
        self.on_enter("restarting↦starting", self._start_and_wait_for_completion)

    async def _stop_and_wait_for_completion(self, event_data: EventData) -> None:
        shutdown_event: Event = anyio.Event()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                partial(event_data.model.stop, shutdown_event=shutdown_event)
            )
            task_group.start_soon(shutdown_event.wait)

    async def _start_and_wait_for_completion(self, event_data: EventData) -> None:
        bootup_event: Event = anyio.Event()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                partial(event_data.model.start, bootup_event=bootup_event)
            )
            task_group.start_soon(bootup_event.wait)

    def _can_restart(self, event_data: EventData) -> bool:
        if event_data.model._state in self.restart_allowed_from:
            return True
        else:
            msg = "{}Can't trigger event {} from state {}!".format(
                event_data.machine.name,
                event_data.event.name,
                event_data.model._state,
            )
            raise MachineError(msg)


class ActorStateMachine(BaseStateMachine):
    transition_cls = AsyncTransitionWithLogging

    # region Dunder methods

    def __init__(
        self,
        actor_state: ActorState | ActorStateMachine = ActorState,
        name: str = "Actor",
        inherited: bool = False,
    ) -> None:
        self._parallel_state_machines: list[BaseStateMachine] = []

        if inherited:
            base_actor_state_machine = actor_state
            super().__init__(
                states=base_actor_state_machine,
                initial=base_actor_state_machine.initial,
                auto_transitions=False,
                send_event=True,
                name=name,
                model_attribute="_state",
                finalize_event=_crash_if_an_error_occurred,
            )
        else:
            super().__init__(
                states=actor_state,
                initial=actor_state.initializing,
                auto_transitions=False,
                send_event=True,
                name=name,
                model_attribute="_state",
                finalize_event=_crash_if_an_error_occurred,
            )

            self._create_bootup_transitions(actor_state)
            self._create_shutdown_transitions(actor_state)
            self._create_restart_transitions(actor_state)
            self._create_crashed_transitions(actor_state)
            self._create_started_substates_transitions(actor_state)

        self._parallel_state_machines.append(ActorRestartStateMachine())

    # endregion

    # region Public API

    def add_model(self, model: str | Actor, initial: Any | None = None) -> None:
        super().add_model(model, initial=initial)

        for machine in self._parallel_state_machines:
            machine.add_model(model, initial=initial)

    def register_parallel_state_machine(self, machine: BaseStateMachine) -> None:
        self._parallel_state_machines.append(machine)

    # endregion

    # region Protected API

    def _create_crashed_transitions(self, actor_state):
        self.add_transition("report_error", "*", actor_state.crashed)
        self.add_transition(
            "stop", actor_state.crashed, actor_state.stopping, after="stop"
        )
        self.add_transition(
            "start", actor_state.crashed, actor_state.starting, after="start"
        )

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
            "stop",
            actor_state.stopping.value.dependencies_stopped,
            actor_state.stopped,
            after=partial(_maybe_set_event, event_name="shutdown_event"),
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
            after=partial(_maybe_set_event, event_name="bootup_event"),
        )

    # endregion


# endregion


async def _release_resources(event_data: EventData) -> None:
    await event_data.model._exit_stack.aclose()


async def _maybe_set_event(event_data: EventData, event_name: str) -> None:
    kwargs = _merge_event_data_kwargs(event_data)
    try:
        event: Event = kwargs[event_name]
        event.set()
    except KeyError:
        pass


async def _crash_if_an_error_occurred(event_data: EventData) -> None:
    error = event_data.error
    if error:
        if event_data.state.value != ActorState.crashed:
            try:
                model = event_data.model

                async with anyio.create_task_group() as task_group:
                    await task_group.spawn(model.abort_restart, error)
                    await task_group.spawn(model.report_error, error)
            except Exception:
                # TODO: Log this
                pass
        else:
            # TODO: Log this
            pass


def _merge_event_data_kwargs(event_data: EventData) -> dict:
    kwargs = event_data.kwargs
    while True:
        args = event_data.args
        if args:
            try:
                event_data = next(arg for arg in args if isinstance(arg, EventData))
            except StopIteration:
                break
            kwargs.update(event_data.kwargs)
        else:
            break
    return kwargs
