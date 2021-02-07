import os
import sys
import typing
from collections import defaultdict
from contextlib import AsyncExitStack
from copy import deepcopy
from uuid import UUID, uuid4

import anyio
from anyio.abc import CapacityLimiter

from jumpstarter.resources import (
    NotAResourceError,
    ResourceAlreadyExistsError,
    ThreadedContextManager,
    is_synchronous_resource,
    resource,
)
from jumpstarter.states import ActorState, ActorStateMachine


class ActorStateMachineFactory(dict):
    def __missing__(self, key: typing.Type):
        # We can't check for actor type during module initialization
        # so we check if the Actor class is already defined instead.
        # If it's not, we simply assume that this is the state machine for the Actor class.
        try:
            Actor
        except NameError:
            state_machine: ActorStateMachine = ActorStateMachine(
                actor_state=key.actor_state, name="Actor"
            )
            self[key] = state_machine
            return state_machine
        else:
            if key is Actor:
                state_machine: ActorStateMachine = ActorStateMachine(
                    actor_state=key.actor_state, name="Actor"
                )
                self[key] = state_machine
                return state_machine

        bases = key.__bases__
        actor_bases = sum(1 for base in bases if issubclass(base, Actor))
        if actor_bases == 0:
            raise TypeError("No base actor found.")

        if actor_bases > 1:
            raise TypeError(
                "Inheritance from multiple Actor base classes is not supported."
            )

        actor_base_class = next(base for base in bases if issubclass(base, Actor))

        if actor_base_class.actor_state is not key.actor_state:
            raise TypeError(
                f"The actor state of {key}, {key.actor_state}, "
                f"must be of the same type as the actor state of {actor_base_class} "
                f"which uses {actor_base_class.actor_state}.\n"
                "Using a different actor state is currently unsupported."
            )

        # We must deepcopy here or otherwise transitions copies the state machine's callbacks by **reference**
        # This results in callbacks registered in one actor ending up in another.
        # TODO: Remove the deepcopy once https://github.com/pytransitions/transitions/issues/509 is resolved
        state_machine: ActorStateMachine = ActorStateMachine(
            actor_state=deepcopy(actor_base_class._state_machine),
            inherited=True,
            name=key.__qualname__,
        )
        self[key] = state_machine
        return state_machine


class Actor:
    # region Class Attributes
    __state_machine: typing.ClassVar[
        ActorStateMachineFactory
    ] = ActorStateMachineFactory()

    actor_state = ActorState

    __global_worker_threads_capacity_limiter = None

    # TODO: Remove this once we drop support for Python < 3.9
    if sys.version_info[1] >= 9:

        @classmethod
        @property
        def _state_machine(cls) -> ActorStateMachine:
            return cls.__state_machine[cls]

    else:
        from jumpstarter.backports import classproperty

        @classproperty
        def _state_machine(cls) -> ActorStateMachine:
            return cls.__state_machine[cls]

    @classmethod
    @property
    def _global_worker_threads_capacity(cls) -> CapacityLimiter:
        if cls.__global_worker_threads_capacity_limiter is None:
            cls.__global_worker_threads_capacity_limiter = (
                anyio.create_capacity_limiter(os.cpu_count())
            )

        return cls.__global_worker_threads_capacity_limiter

    # endregion

    # region Dunder methods

    def __init__(self, *, actor_id: typing.Optional[typing.Union[str, UUID]] = None):
        cls: typing.Type = type(self)
        cls._state_machine.add_model(self)

        self._exit_stack: AsyncExitStack = AsyncExitStack()

        self._resources: typing.Dict[str, typing.Optional[typing.Any]] = defaultdict(
            lambda: None
        )
        self.__actor_id = actor_id or uuid4()

    def __init_subclass__(
        cls, *, actor_state: typing.Optional[ActorState] = ActorState
    ):
        cls.actor_state = actor_state

        if not issubclass(actor_state, ActorState):
            raise TypeError(
                f"Actor states must be ActorState or a child class of it. Instead we got {actor_state.__name__}."
            )

    # endregion

    # region Public API

    @property
    def state(self) -> typing.Union[typing.Dict[str, typing.Any], typing.Any]:
        parallel_states = {
            machine.name[:-2]: machine.get_model_state(self)
            for machine in self._state_machine._parallel_state_machines
        }

        if parallel_states:
            parallel_states[self._state_machine.name[:-2]] = self._state
            return parallel_states

        return self._state

    @property
    def actor_id(self):
        return self.__actor_id

    async def manage_resource_lifecycle(
        self, resource: typing.AsyncContextManager, name: str
    ) -> None:
        if self._resources.get(name, None):
            raise ResourceAlreadyExistsError(name, self._resources[name])

        if is_synchronous_resource(resource):
            cls = type(self)
            resource = ThreadedContextManager(
                resource, cls._global_worker_threads_capacity
            )

        try:
            self._resources[name] = await self._exit_stack.enter_async_context(resource)
        except AttributeError as e:
            raise NotAResourceError(name, resource) from e

        self._exit_stack.push(lambda *_: self._cleanup_resource(name))

    # endregion

    # region Resources

    @resource
    def cancel_scope(self):
        return anyio.open_cancel_scope()

    # endregion

    # region Protected API

    def _cleanup_resource(self, name: str) -> None:
        del self._resources[name]

    # endregion

    # region Class Public API

    @classmethod
    def draw_state_machine_graph(cls, path: str) -> None:
        graph = cls._state_machine.get_graph()
        graph.node_attr["style"] = "filled"

        # Node colors
        for node in graph.iternodes():
            name: str = str(node)
            if name in ("initializing", "initialized"):
                node.attr["fillcolor"] = "#fcf8e8"
            elif name.startswith("starting"):
                node.attr["fillcolor"] = "#74c7b8"
            elif name.startswith("started"):
                color = "#16c79a"
                if name.endswith("degraded"):
                    color = "#ffc764"
                elif name.endswith("unhealthy"):
                    color = "#ef4f4f"
                node.attr["fillcolor"] = color
            elif name.startswith("stopping"):
                node.attr["fillcolor"] = "#ee9595"
            elif name in ("stopped", "crashed"):
                node.attr["fillcolor"] = "#ef4f4f"

        # Edge colors
        for edge in graph.iteredges():
            destination: str = edge[1]
            if destination in ("crashed", "stopped"):
                edge.attr["color"] = "#ef4f4f"
            elif destination == "initialized":
                edge.attr["color"] = "#ffc764"
            elif destination.startswith("starting"):
                edge.attr["color"] = "#74c7b8"
            elif destination.startswith("started"):
                color = "#16c79a"
                if destination.endswith("degraded"):
                    color = "#ffc764"
                elif destination.endswith("unhealthy"):
                    color = "#ef4f4f"
                edge.attr["color"] = color
            elif destination.startswith("stopping"):
                edge.attr["color"] = "#ee9595"

        graph.draw(path, prog="circo")

    # endregion
