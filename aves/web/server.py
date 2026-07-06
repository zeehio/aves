# -*- coding: utf-8 -*-
"""
A thin web view, parallel to aves.gui: given data, display it -- here,
by streaming it to any connected browser instead of drawing it with
matplotlib. Knows nothing about how data is acquired.

create_app(gui_config) returns a FastAPI app exposing:

 - GET /api/config: the same gui section SensorViewerGUI would be
   built from (x_column, axes, ...), as JSON, so a browser can lay out
   the same charts without any acquisition-side changes.
 - WS /ws/data: streams each message published to app.state.broadcaster
   to every connected client. Whatever drives acquisition (a background
   thread running aves.acquisition.Acquisition, in the intended use)
   calls app.state.broadcaster.publish(data) after each step -- this
   module has no opinion on what that data source is.
 - /: the frontend (static/index.html + static/app.js), served as-is,
   no build step. Reads /api/config to lay out one chart per configured
   axis, then appends data as it arrives over /ws/data.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from aves.web.broadcaster import Broadcaster

STATIC_DIR = Path(__file__).parent / "static"


def create_app(gui_config):
    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app):
        broadcaster.bind_loop()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.broadcaster = broadcaster

    @app.get("/api/config")
    async def get_config():
        return gui_config

    @app.websocket("/ws/data")
    async def stream_data(websocket: WebSocket):
        await websocket.accept()
        queue = await broadcaster.subscribe()
        try:
            while True:
                message = await queue.get()
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unsubscribe(queue)

    # Mounted last: /api/config and /ws/data above are matched first since
    # routes are tried in registration order, so this catch-all can't shadow them.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
