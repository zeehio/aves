import asyncio
import threading

import pytest

from aves.web.broadcaster import Broadcaster


def test_broadcaster_delivers_to_a_subscribed_queue():
    async def scenario():
        broadcaster = Broadcaster()
        broadcaster.bind_loop()
        queue = await broadcaster.subscribe()
        broadcaster.publish({"x": 1})
        assert await queue.get() == {"x": 1}
    asyncio.run(scenario())


def test_broadcaster_delivers_to_every_subscriber():
    async def scenario():
        broadcaster = Broadcaster()
        broadcaster.bind_loop()
        q1 = await broadcaster.subscribe()
        q2 = await broadcaster.subscribe()
        broadcaster.publish({"x": 1})
        assert await q1.get() == {"x": 1}
        assert await q2.get() == {"x": 1}
    asyncio.run(scenario())


def test_broadcaster_unsubscribe_stops_delivery():
    async def scenario():
        broadcaster = Broadcaster()
        broadcaster.bind_loop()
        queue = await broadcaster.subscribe()
        broadcaster.unsubscribe(queue)
        broadcaster.publish({"x": 1})
        await asyncio.sleep(0)  # let any (wrongly) scheduled callback run
        assert queue.empty()
    asyncio.run(scenario())


def test_broadcaster_publish_before_bind_loop_raises():
    broadcaster = Broadcaster()
    with pytest.raises(RuntimeError, match="bind_loop"):
        broadcaster.publish({"x": 1})


def test_broadcaster_ready_is_set_only_after_bind_loop():
    async def scenario():
        broadcaster = Broadcaster()
        assert not broadcaster.ready.is_set()
        broadcaster.bind_loop()
        assert broadcaster.ready.is_set()
    asyncio.run(scenario())


def test_broadcaster_publish_is_safe_from_a_different_thread():
    """The realistic scenario this class exists for: publish() is
    called from the thread running the blocking acquisition loop, not
    from the thread running the event loop."""
    async def scenario():
        broadcaster = Broadcaster()
        broadcaster.bind_loop()
        queue = await broadcaster.subscribe()

        thread = threading.Thread(target=broadcaster.publish, args=({"x": 1},))
        thread.start()
        thread.join()

        message = await asyncio.wait_for(queue.get(), timeout=2)
        assert message == {"x": 1}
    asyncio.run(scenario())
