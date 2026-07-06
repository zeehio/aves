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
 - GET/PUT /api/settings, POST /api/settings/load, POST
   /api/settings/restart: the config file editor. This module only
   reads/writes text and validates TOML syntax + the 'version' key; it
   has no opinion on what a valid 'gui'/'input'/'output' section looks
   like beyond that -- restarting is where the real, structural
   validation happens (aves.wiring raising a clear error), via whatever
   restart_callback the caller wires up (aves.web.__main__ wires this
   to actually stop/rebuild/restart the acquisition; without one, the
   restart endpoint just reports that restarting isn't supported).
 - /: the frontend (static/index.html + static/app.js), served as-is,
   no build step. Reads /api/config to lay out one chart per configured
   axis, then appends data as it arrives over /ws/data.

This exposes local file read/write (the config file, and whatever path
/api/settings/load is given) -- fine for the intended local-only
(127.0.0.1) use, since the person running the process already has that
level of access, but a reason not to bind --host to anything else.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aves.utils import parse_config_text
from aves.web.broadcaster import Broadcaster

STATIC_DIR = Path(__file__).parent / "static"

#: Sentinel published to every connected browser after a successful
#: restart, so open chart tabs reload and rebuild against the (possibly
#: different) axes/columns of the newly (re)loaded config, instead of
#: silently rendering stale/mismatched charts.
CONFIG_CHANGED_MESSAGE = {"__aves_config_changed__": True}


class SettingsText(BaseModel):
    text: str


class SettingsPath(BaseModel):
    path: str


def create_app(gui_config, config_path=None):
    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app):
        broadcaster.bind_loop()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.broadcaster = broadcaster
    app.state.gui_config = gui_config
    app.state.config_path = config_path
    # Set by the caller (aves.web.__main__.main) if it wants
    # /api/settings/restart to actually do something; left unset, that
    # endpoint reports restarting as unsupported rather than pretending
    # to succeed. Signature: restart_callback(config_path) -> gui_config.
    app.state.restart_callback = None

    @app.get("/api/config")
    async def get_config():
        return app.state.gui_config

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

    @app.get("/api/settings")
    async def get_settings():
        if app.state.config_path is None:
            raise HTTPException(
                status_code=404,
                detail="this server was not started with a config file")
        try:
            text = Path(app.state.config_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"path": app.state.config_path, "text": text}

    @app.put("/api/settings")
    async def save_settings(payload: SettingsText):
        if app.state.config_path is None:
            raise HTTPException(
                status_code=400,
                detail="this server was not started with a config file")
        try:
            parse_config_text(payload.text, source_name=app.state.config_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            Path(app.state.config_path).write_text(payload.text, encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"path": app.state.config_path}

    @app.post("/api/settings/load")
    async def load_settings(payload: SettingsPath):
        try:
            text = Path(payload.path).read_text(encoding="utf-8")
            parse_config_text(text, source_name=payload.path)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        app.state.config_path = payload.path
        return {"path": payload.path, "text": text}

    @app.post("/api/settings/restart")
    async def restart_acquisition():
        if app.state.restart_callback is None:
            raise HTTPException(
                status_code=400,
                detail="this server was not started with restart support")
        loop = asyncio.get_running_loop()
        try:
            new_gui_config = await loop.run_in_executor(
                None, app.state.restart_callback, app.state.config_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        app.state.gui_config = new_gui_config
        broadcaster.publish(CONFIG_CHANGED_MESSAGE)
        return {"status": "restarted"}

    # Mounted last: /api/config and /ws/data above are matched first since
    # routes are tried in registration order, so this catch-all can't shadow them.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
