# -*- coding: utf-8 -*-
"""
Fans out published messages to any number of connected asyncio consumers
(one asyncio.Queue per subscriber). This is the web equivalent of
SensorViewerGUI.render(): a pure sink that knows nothing about
acquisition, matching the same "same data, different consumer" boundary
aves.acquisition already established for the matplotlib GUI.

The one real wrinkle a web view has that the matplotlib GUI doesn't:
publish() is called from the thread running the blocking acquisition
loop (see aves.wiring/aves.acquisition), not from the event loop's own
thread. asyncio.Queue is not thread-safe, so publish() schedules
delivery via loop.call_soon_threadsafe() instead of touching the queues
directly.
"""

import asyncio
import threading


class Broadcaster:
    def __init__(self):
        self._loop = None
        self._clients = set()
        #: Set once bind_loop() has run. A producer thread started before
        #: the server's event loop exists (e.g. an acquisition thread
        #: launched right before uvicorn.run()) should wait on this
        #: before calling publish(), instead of racing bind_loop().
        self.ready = threading.Event()

    def bind_loop(self, loop=None):
        """
        Call once, from the event loop's own thread (e.g. at server
        startup), so publish() knows which loop to schedule delivery on.
        """
        self._loop = loop if loop is not None else asyncio.get_running_loop()
        self.ready.set()

    async def subscribe(self):
        """
        Registers a new client, returning the queue it should read
        published messages from. Call from the event loop's thread.
        """
        queue = asyncio.Queue()
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._clients.discard(queue)

    def publish(self, message):
        """
        Delivers message to every currently-subscribed client. Safe to
        call from any thread, including one that isn't running the
        event loop.
        """
        if self._loop is None:
            raise RuntimeError("Broadcaster.bind_loop() was never called")
        for queue in list(self._clients):
            self._loop.call_soon_threadsafe(queue.put_nowait, message)
