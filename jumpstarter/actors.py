import typing
from collections import defaultdict
from contextlib import AsyncExitStack
from typing import ClassVar

import anyio
from anyio.abc import CancelScope

from jumpstarter.states import ActorStateMachine

# region STATES


# class ActorRestartState(Enum):
#     starting = auto()
#     stopping = auto()
#     stopped = auto()


# endregion


class Actor:
    __state_machine: ClassVar[
        typing.Dict[typing.Type, ActorStateMachine]
    ] = defaultdict(ActorStateMachine)

    @classmethod
    @property
    def _state_machine(cls) -> ActorStateMachine:
        return cls._Actor__state_machine[cls]

    def __init__(self):
        cls: Type = type(self)
        cls._state_machine.add_model(self)

        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._cancel_scope: CancelScope = anyio.open_cancel_scope()

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
