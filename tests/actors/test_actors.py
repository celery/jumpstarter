from uuid import UUID

import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import ActorState

pytestmark = pytest.mark.anyio


async def test_actor_id_is_a_uuid():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor()

    assert fake_actor.actor_id
    assert isinstance(fake_actor.actor_id, UUID)


async def test_actor_can_transition_back_to_starting_after_stopped():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor()

    assert fake_actor.state == ActorState.initializing

    await fake_actor.start()
    assert fake_actor.state == ActorState.started

    await fake_actor.stop()
    assert fake_actor.state == ActorState.stopped

    await fake_actor.start()
    assert fake_actor.state == ActorState.started
