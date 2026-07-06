# -*- coding: utf-8 -*-
"""
A thin web view, parallel to aves.gui: given data, display it -- here,
by streaming it to any connected browser instead of drawing it with
matplotlib. Knows nothing about how data is acquired.

create_app(gui_config, token=...) returns a FastAPI app exposing:

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
 - /, /settings.html: the frontend's two pages, rendered (not served
   verbatim) so the auth token can be embedded for the page's own JS to
   send back. /app.js, /settings.js, /style.css, /vendor/*: plain
   static files -- just code/assets, nothing sensitive, so these are
   never token-gated.

Auth: if `token` is given, every /api/* route and /ws/data require it,
since those touch acquired data and arbitrary local file read/write
(the config path, and whatever path /api/settings/load is given) --
this is meant to run on 127.0.0.1 for one trusted user, but the token
means a stray port scan or another local user can't quietly read/write
through it. A browser page proves it has the token by loading / or
/settings.html with ?token=..., which sets a session cookie (so plain
link clicks and the WebSocket handshake, which can't carry a custom
header, keep working); the page's own JS additionally sends the token
as `Authorization: Bearer <token>` on every fetch() call, since that's
the more explicit mechanism to depend on. Either is accepted. token=None
(or "") disables all of this -- only for trusted, fully local use.
"""

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aves.utils import parse_config_text
from aves.web.broadcaster import Broadcaster

STATIC_DIR = Path(__file__).parent / "static"
TOKEN_COOKIE = "aves_token"

#: Sentinel published to every connected browser after a successful
#: restart, so open chart tabs reload and rebuild against the (possibly
#: different) axes/columns of the newly (re)loaded config, instead of
#: silently rendering stale/mismatched charts.
CONFIG_CHANGED_MESSAGE = {"__aves_config_changed__": True}


class SettingsText(BaseModel):
    text: str


class SettingsPath(BaseModel):
    path: str


def _token_matches(expected, given):
    return bool(given) and secrets.compare_digest(given, expected)


def _token_from_request(request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[len("bearer "):]
    cookie_token = request.cookies.get(TOKEN_COOKIE)
    if cookie_token:
        return cookie_token
    return request.query_params.get("token")


def create_app(gui_config, config_path=None, token=None):
    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app):
        broadcaster.bind_loop()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.broadcaster = broadcaster
    app.state.gui_config = gui_config
    app.state.config_path = config_path
    app.state.token = token or None
    # Set by the caller (aves.web.__main__.main) if it wants
    # /api/settings/restart to actually do something; left unset, that
    # endpoint reports restarting as unsupported rather than pretending
    # to succeed. Signature: restart_callback(config_path) -> gui_config.
    app.state.restart_callback = None

    def require_token(request: Request):
        if app.state.token is None:
            return
        if not _token_matches(app.state.token, _token_from_request(request)):
            raise HTTPException(status_code=401, detail="missing or invalid token")

    def _render_page(request, filename):
        if app.state.token is not None:
            if not _token_matches(app.state.token, _token_from_request(request)):
                raise HTTPException(status_code=401, detail="missing or invalid token")
        html = (STATIC_DIR / filename).read_text(encoding="utf-8")
        # json.dumps + escaping "</" keeps this safe to embed inside a
        # <script> block even for an unusual custom --token value (the
        # auto-generated default is URL-safe base64, needing none of this,
        # but a user-supplied token is untrusted input).
        token_json = json.dumps(app.state.token or "").replace("</", "<\\/")
        html = html.replace("__AVES_TOKEN_JSON__", token_json)
        response = HTMLResponse(html)
        if app.state.token is not None:
            response.set_cookie(
                TOKEN_COOKIE, app.state.token, httponly=True, samesite="lax")
        return response

    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    async def index(request: Request):
        # Both paths need their own route (not just "/"): a direct
        # request for "/index.html" would otherwise fall through to the
        # unauthenticated static mount below, since that file genuinely
        # exists in STATIC_DIR.
        return _render_page(request, "index.html")

    @app.get("/settings.html", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return _render_page(request, "settings.html")

    @app.get("/api/config", dependencies=[Depends(require_token)])
    async def get_config():
        return app.state.gui_config

    @app.websocket("/ws/data")
    async def stream_data(websocket: WebSocket):
        if app.state.token is not None:
            given = websocket.cookies.get(TOKEN_COOKIE) or websocket.query_params.get("token")
            if not _token_matches(app.state.token, given):
                await websocket.close(code=4401)
                return
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

    @app.get("/api/settings", dependencies=[Depends(require_token)])
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

    @app.put("/api/settings", dependencies=[Depends(require_token)])
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

    @app.post("/api/settings/load", dependencies=[Depends(require_token)])
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

    @app.post("/api/settings/restart", dependencies=[Depends(require_token)])
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

    # Mounted last, and no longer covers index.html/settings.html (served
    # above instead, so the token can be embedded): /api/*, /ws/data, /,
    # and /settings.html are all matched first since routes are tried in
    # registration order, so this catch-all can't shadow them.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
