import os
import sys
import typing
from collections import defaultdict
from contextlib import AsyncExitStack
from uuid import uuid4

import anyio
from anyio.abc import CancelScope, CapacityLimiter
from diskcache import Cache

from jumpstarter.resources import (
    NotAResourceError,
    ResourceAlreadyExistsError,
    ThreadedContextManager,
    is_synchronous_resource,
    resource,
)
from jumpstarter.states import ActorStateMachine


class Actor:
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

    def __init__(self, cache_directory=None):
        cls: typing.Type = type(self)
        cls._state_machine.add_model(self)

        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._cache = Cache(directory=cache_directory)
        self._cancel_scope: CancelScope = anyio.open_cancel_scope()

        self._resources: typing.Dict[str, typing.Optional[typing.Any]] = defaultdict(
            lambda: None
        )
        self.__actor_id = uuid4()

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

    @resource
    def cache(self):
        return self._cache

    def _cleanup_resource(self, name: str) -> None:
        del self._resources[name]

    @classmethod
    def draw_state_machine_graph(cls, path: str) -> None:
        cls._state_machine.get_graph().draw(path, prog="dot")
