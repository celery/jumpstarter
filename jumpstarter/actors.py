import typing
from contextlib import AsyncExitStack
from functools import partial, wraps
from typing import ClassVar

import anyio
from anyio.abc import CancelScope
from transitions.extensions.nesting import NestedState

from jumpstarter.resources import NotAResourceError
from jumpstarter.states import ActorStartingState, ActorStateMachine

NestedState.separator = "↦"


# region STATES


# class ActorRestartState(Enum):
#     starting = auto()
#     stopping = auto()
#     stopped = auto()


# endregion


class Actor:
    _state_machine: ClassVar[ActorStateMachine] = ActorStateMachine()

    def __init__(self):
        cls = type(self)
        cls._state_machine.add_model(self)

        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._cancel_scope: CancelScope = anyio.open_cancel_scope()

    def __init_subclass__(cls, **kwargs):
        cls._state_machine = ActorStateMachine()

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
                    this_transition.before.extend(that_transition.before)
                    this_transition.after.extend(
                        filter(lambda x: x not in ("start", "stop"), that_transition.after)
                    )

    @classmethod
    def acquire_resource(
        cls,
        resource_callback: typing.Optional[typing.Callable] = None,
        *,
        timeout: typing.Optional[float] = None,
    ) -> typing.Callable:
        if resource_callback is None:
            return partial(cls.acquire_resource, timeout=timeout)

        if timeout:

            @wraps(resource_callback)
            async def resource_acquirer(event_data):
                self = event_data.model
                resource = resource_callback(self)

                try:
                    async with anyio.fail_after(timeout):
                        await self._exit_stack.enter_async_context(resource)
                except AttributeError as e:
                    raise NotAResourceError(resource_callback, resource) from e

        else:

            @wraps(resource_callback)
            async def resource_acquirer(event_data):
                self = event_data.model
                resource = resource_callback(self)

                try:
                    await self._exit_stack.enter_async_context(resource)
                except AttributeError as e:
                    raise NotAResourceError(resource_callback, resource) from e

        transition = cls._state_machine.get_transitions(
            "start",
            ActorStartingState.dependencies_started,
            ActorStartingState.resources_acquired,
        )[0]
        transition.before.append(resource_acquirer)

        return resource_callback
