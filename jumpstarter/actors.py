import os
import sys
import typing
from collections import defaultdict
from contextlib import AsyncExitStack
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
from jumpstarter.states import ActorStateMachine


class Actor:
    # region Class Attributes
    __state_machine: typing.ClassVar[
        typing.Dict[typing.Type, ActorStateMachine]
    ] = defaultdict(ActorStateMachine)

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

    def __init_subclass__(cls, **kwargs):
        for base in cls.__bases__:
            base_state_machine = getattr(base, "_state_machine", None)

            if base_state_machine:
                for this_state, that_state in zip(
                    cls._state_machine.states.values(),
                    base_state_machine.states.values(),
                ):
                    this_state.on_enter.extend(that_state.on_enter)
                    this_state.on_exit.extend(that_state.on_exit)

                for this_transition, that_transition in zip(
                    cls._state_machine.get_transitions(),
                    base_state_machine.get_transitions(),
                ):
                    this_transition.prepare.extend(that_transition.prepare)
                    this_transition.before.extend(
                        list(
                            filter(
                                lambda x: getattr(x, "__name__", None)
                                != "_release_resources",
                                that_transition.before,
                            )
                        )
                    )
                    this_transition.after.extend(
                        list(
                            filter(
                                lambda x: x not in ("start", "stop"),
                                that_transition.after,
                            )
                        )
                    )

    # endregion

    # region Public API

    @property
    def actor_id(self):
        return self.__actor_id

    async def manage_resource_lifecycle(
        self, resource: typing.AsyncContextManager, name: str
    ) -> None:
        if self._resources.get(name, None):
            raise ResourceAlreadyExistsError(name)

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
        graph.node_attr['style'] = 'filled'

        # Node colors
        for node in graph.iternodes():
            name: str = str(node)
            if name in ('initializing', 'initialized'):
                node.attr['fillcolor'] = "#fcf8e8"
            elif name.startswith('starting'):
                node.attr['fillcolor'] = "#74c7b8"
            elif name.startswith('started'):
                color = "#16c79a"
                if name.endswith('degraded'):
                    color = "#ffc764"
                elif name.endswith("unhealthy"):
                    color = "#ef4f4f"
                node.attr['fillcolor'] = color
            elif name.startswith('stopping'):
                node.attr['fillcolor'] = "#ee9595"
            elif name in ('stopped', 'crashed'):
                node.attr['fillcolor'] = "#ef4f4f"

        # Edge colors
        for edge in graph.iteredges():
            destination: str = edge[1]
            if destination in ('crashed', 'stopped'):
                edge.attr['color'] = "#ef4f4f"
            elif destination == 'initialized':
                edge.attr['color'] = "#ffc764"
            elif destination.startswith('starting'):
                edge.attr['color'] = "#74c7b8"
            elif destination.startswith('started'):
                color = "#16c79a"
                if destination.endswith('degraded'):
                    color = "#ffc764"
                elif destination.endswith("unhealthy"):
                    color = "#ef4f4f"
                edge.attr['color'] = color
            elif destination.startswith('stopping'):
                edge.attr['color'] = "#ee9595"

        graph.draw(path, prog="circo")

    # endregion
