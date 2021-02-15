from __future__ import annotations

import typing
from functools import partial
from functools import wraps

import anyio
import transitions
from anyio.abc import CapacityLimiter
from wrapt import ObjectProxy

from jumpstarter.states import ActorStartingState

__all__ = (
    "NotAResourceError",
    "ResourceAlreadyExistsError",
    "ResourceUnavailable",
    "resource",
    "ThreadedContextManager",
    "is_synchronous_resource",
)


class NotAResourceError(Exception):
    def __init__(self, resource_name: str, return_value: typing.Any) -> None:
        super().__init__(
            f"The return value of {resource_name} is not a context manager.\n"
            f"Instead we got {return_value}.")


class ResourceAlreadyExistsError(Exception):
    pass


class ResourceUnavailable(Exception):
    pass


def is_synchronous_resource(
    resource: typing.ContextManager | typing.AsyncContextManager, ) -> bool:
    return isinstance(resource, typing.ContextManager) and not isinstance(
        resource, typing.AsyncContextManager)


class Resource:
    def __init__(self,
                 resource_callback: typing.Callable,
                 timeout: float = None):
        self._resource_callback: typing.Callable = resource_callback
        self._timeout: float = timeout

        self._name: str | None = None

    def __set_name__(self, owner, name):
        self._name = name

        if self._timeout:

            @wraps(self._resource_callback)
            async def resource_acquirer(
                    event_data: transitions.EventData) -> None:
                self_ = event_data.model

                try:
                    resource = self._resource_callback(self_)
                except ResourceUnavailable:
                    return

                if is_synchronous_resource(resource):
                    raise TypeError(
                        "Specifying a timeout is not supported while acquiring a synchronous resource.\n"
                        f"You should either remove the timeout keyword argument from the definition of {name} or replace it with an asynchronous resource."
                    )

                async with anyio.fail_after(self._timeout):
                    await self_.manage_resource_lifecycle(resource, name)

        else:

            @wraps(self._resource_callback)
            async def resource_acquirer(
                    event_data: transitions.EventData) -> None:
                self_ = event_data.model

                try:
                    resource = self._resource_callback(self_)
                except ResourceUnavailable:
                    return

                await self_.manage_resource_lifecycle(resource, name)

        # TODO: Figure out how to encapsulate the registration the callbacks

        transition = owner._state_machine.get_transitions(
            "start",
            ActorStartingState.dependencies_started,
            ActorStartingState.resources_acquired,
        )[0]
        transition.before.append(resource_acquirer)

        setattr(owner, f"__{name}", self._resource_callback)
        setattr(owner, name, self)

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")

    def __get__(self, instance, owner):
        if instance:
            return instance._resources[self._name]


class ThreadedContextManager(ObjectProxy):
    def __init__(self, context_manager: typing.ContextManager,
                 capacity_limiter: CapacityLimiter):
        super().__init__(context_manager)
        self._capacity_limiter = capacity_limiter

    async def __aenter__(self) -> typing.Any:
        return await anyio.run_sync_in_worker_thread(
            self.__wrapped__.__enter__, limiter=self._capacity_limiter)

    async def __aexit__(self, *exc_info) -> bool | None:
        return await anyio.run_sync_in_worker_thread(
            self.__wrapped__.__exit__,
            *exc_info,
            limiter=self._capacity_limiter)


def resource(
    resource_callback: typing.Callable | None = None,
    *,
    timeout: float | None = None,
) -> partial[Resource] | Resource:
    if resource_callback is None:
        return partial(Resource, timeout=timeout)

    return Resource(resource_callback)
