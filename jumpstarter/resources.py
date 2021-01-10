from __future__ import annotations

import typing
from functools import partial, wraps

import anyio
import transitions

from jumpstarter.states import ActorStartingState, ActorStoppingState

__all__ = ("NotAResourceError", "resource")


class NotAResourceError(Exception):
    def __init__(self, resource_callback: typing.Callable, return_value):
        super(NotAResourceError, self).__init__(
            f"The return value of {resource_callback.__name__} is not a context manager.\n"
            f"Instead we got {return_value}."
        )


class Resource:
    def __init__(self, resource_callback: typing.Callable, timeout: float = None):
        self._resource_callback: typing.Callable = resource_callback
        self._timeout: float = timeout

        self._name: typing.Optional[str] = None

    def __set_name__(self, owner, name):
        self._name = name

        if self._timeout:

            @wraps(self._resource_callback)
            async def resource_acquirer(event_data: transitions.EventData) -> None:
                self_ = event_data.model

                resource = self._resource_callback(self_)
                self_._resources[name] = resource

                try:
                    async with anyio.fail_after(self._timeout):
                        await self_.manage_resource_lifecycle(resource)
                except AttributeError as e:
                    raise NotAResourceError(self._resource_callback, resource) from e

        else:

            @wraps(self._resource_callback)
            async def resource_acquirer(event_data: transitions.EventData) -> None:
                self_ = event_data.model

                resource = self._resource_callback(self_)
                self_._resources[name] = resource

                try:
                    await self_.manage_resource_lifecycle(resource)
                except AttributeError as e:
                    raise NotAResourceError(self._resource_callback, resource) from e

        transition = owner._state_machine.get_transitions(
            "start",
            ActorStartingState.dependencies_started,
            ActorStartingState.resources_acquired,
        )[0]
        transition.before.append(resource_acquirer)

        def _cleanup_resource(event_data: transitions.EventData) -> None:
            self_ = event_data.model
            del self_._resources[name]

        transition = owner._state_machine.get_transitions(
            "stop",
            ActorStoppingState.tasks_stopped,
            ActorStoppingState.resources_released,
        )[0]
        transition.before.append(_cleanup_resource)

        setattr(owner, f"__{name}", self._resource_callback)
        setattr(owner, name, self)

    def __set__(self, instance, value):
        raise AttributeError("can't set attribute")

    def __get__(self, instance, owner):
        if instance:
            return instance._resources[self._name]


def resource(
    resource_callback: typing.Callable = None, *, timeout: float = None
) -> typing.Union[partial[Resource], Resource]:
    if resource_callback is None:
        return partial(Resource, timeout=timeout)

    return Resource(resource_callback)
