from uuid import UUID

import pytest

from jumpstarter import Actor
from jumpstarter.states import ActorRunningState, ActorStartedState, ActorState

pytestmark = pytest.mark.anyio


async def test_actor_id_is_a_uuid_by_default():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor()

    assert fake_actor.actor_id
    assert isinstance(fake_actor.actor_id, UUID)


async def test_actor_id_is_set():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor(actor_id="fake_actor")

    assert fake_actor.actor_id == "fake_actor"
    assert isinstance(fake_actor.actor_id, str)


async def test_actor_can_transition_back_to_starting_after_stopped():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor()

    assert fake_actor.state == ActorState.initializing

    await fake_actor.start()
    assert fake_actor.state == ActorRunningState.healthy

    await fake_actor.stop()
    assert fake_actor.state == ActorState.stopped

    await fake_actor.start()
    assert fake_actor.state == ActorRunningState.healthy


async def test_actor_can_pause_and_resume_after_start():
    class FakeActor(Actor):
        ...

    fake_actor = FakeActor()

    assert fake_actor.state == ActorState.initializing

    await fake_actor.start()
    assert fake_actor.state == ActorRunningState.healthy

    await fake_actor.pause()
    assert fake_actor.state == ActorStartedState.paused

    await fake_actor.resume()
    assert fake_actor.state == ActorRunningState.healthy
