import pytest

from jumpstarter.actors import Actor
from jumpstarter.states import diagrams

pytestmark = pytest.mark.anyio


@pytest.mark.skipif(not diagrams, reason="pygraphviz is not installed")
async def test_draw_state_machine_diagram():
    actor = Actor()
    actor.draw_state_machine_graph("state_machine.png")
