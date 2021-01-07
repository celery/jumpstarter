from __future__ import annotations

import typing
from functools import partial, wraps

import anyio

from jumpstarter.states import ActorStartingState

__all__ = ("NotAResourceError", "resource")


class NotAResourceError(Exception):
    def __init__(self, resource_callback: typing.Callable, return_value):
        super(NotAResourceError, self).__init__(
            f"The return value of {resource_callback.__name__} is not a context manager.\n"
            f"Instead we got {return_value}."
        )


class Resource:
    def __init__(self, resource_callback: typing.Callable, timeout: float = None):
        self._resource_callback = resource_callback
        self._timeout = timeout

    def __set_name__(self, owner, name):
        if self._timeout:

            @wraps(self._resource_callback)
            async def resource_acquirer(event_data):
                self_ = event_data.model

                assert owner == type(self_)

                resource = self._resource_callback(self_)

                try:
                    async with anyio.fail_after(self._timeout):
                        await self_._exit_stack.enter_async_context(resource)
                except AttributeError as e:
                    raise NotAResourceError(self_._resource_callback, resource) from e

        else:

            @wraps(self._resource_callback)
            async def resource_acquirer(event_data):
                self_ = event_data.model

                assert owner == type(self_)

                resource = self._resource_callback(self_)

                try:
                    await self_._exit_stack.enter_async_context(resource)
                except AttributeError as e:
                    raise NotAResourceError(self._resource_callback, resource) from e

        transition = owner._state_machine.get_transitions(
            "start",
            ActorStartingState.dependencies_started,
            ActorStartingState.resources_acquired,
        )[0]
        transition.before.append(resource_acquirer)

        setattr(owner, f"__{name}", self._resource_callback)


def resource(
    resource_callback: typing.Callable = None, *, timeout: float = None
) -> typing.Union[partial[Resource], Resource]:
    if resource_callback is None:
        return partial(Resource, timeout=timeout)

    return Resource(resource_callback)
