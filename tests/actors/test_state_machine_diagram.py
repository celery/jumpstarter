import pytest

from jumpstarter.actors import Actor

pytestmark = pytest.mark.anyio


async def test_draw_state_machine_diagram():
    actor = Actor()
    actor.draw_state_machine_graph("state_machine.png")
