from fastapi.testclient import TestClient

from aves.web.server import create_app

VALID_CONFIG_TEXT = 'version = 3\n\n[gui]\nx_column = "t"\naxes = []\n'
VALID_CONFIG_JSON_TEXT = '{"version": 3, "gui": {"x_column": "t", "axes": []}}'


def test_get_config_returns_the_gui_config_as_is():
    gui_config = {"x_column": "t", "zoom_all_together": True, "axes": []}
    app = create_app(gui_config)

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == gui_config


def test_ws_data_streams_published_messages():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        with client.websocket_connect("/ws/data") as websocket:
            # This runs the app (and its event loop) in a background
            # thread managed by TestClient, so publishing from here is a
            # realistic stand-in for the acquisition thread publishing
            # from outside the event loop's thread.
            app.state.broadcaster.publish({"t": [0, 1], "a": [1.0, 2.0]})
            message = websocket.receive_json()

    assert message == {"t": [0, 1], "a": [1.0, 2.0]}


def test_ws_data_fans_out_to_multiple_connected_clients():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        with client.websocket_connect("/ws/data") as ws1, \
                client.websocket_connect("/ws/data") as ws2:
            app.state.broadcaster.publish({"value": 42})
            assert ws1.receive_json() == {"value": 42}
            assert ws2.receive_json() == {"value": 42}


def test_root_serves_the_frontend_index_page():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "app.js" in response.text


def test_static_assets_are_served_including_vendored_uplot():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        app_js = client.get("/app.js")
        uplot_js = client.get("/vendor/uplot/uPlot.iife.min.js")

    assert app_js.status_code == 200
    assert uplot_js.status_code == 200


def test_get_settings_requires_a_config_path():
    app = create_app({"x_column": "t", "axes": []}, config_path=None)

    with TestClient(app) as client:
        response = client.get("/api/settings")

    assert response.status_code == 404


def test_get_settings_returns_the_file_content(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"path": str(config_file), "text": VALID_CONFIG_TEXT}


def test_put_settings_writes_valid_text_to_disk(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))
    new_text = VALID_CONFIG_TEXT + '\n[output]\ncolumns = ["a"]\n'

    with TestClient(app) as client:
        response = client.put("/api/settings", json={"text": new_text})

    assert response.status_code == 200
    assert config_file.read_text() == new_text


def test_put_settings_rejects_invalid_toml_without_touching_disk(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.put("/api/settings", json={"text": "not valid toml ["})

    assert response.status_code == 400
    assert config_file.read_text() == VALID_CONFIG_TEXT


def test_put_settings_rejects_wrong_version(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.put("/api/settings", json={"text": "version = 1\n"})

    assert response.status_code == 400
    assert config_file.read_text() == VALID_CONFIG_TEXT


def test_get_settings_structured_requires_a_config_path():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        response = client.get("/api/settings/structured")

    assert response.status_code == 404


def test_get_settings_structured_returns_the_parsed_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.get("/api/settings/structured")

    assert response.status_code == 200
    assert response.json() == {
        "path": str(config_file),
        "config": {"version": 3, "gui": {"x_column": "t", "axes": []}},
    }


def test_put_settings_structured_writes_json_to_disk(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(VALID_CONFIG_JSON_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))
    new_config = {"version": 3, "gui": {"x_column": "time", "axes": []}}

    with TestClient(app) as client:
        response = client.put("/api/settings/structured", json={"config": new_config})

    assert response.status_code == 200
    from aves.utils import parse_config_text
    assert parse_config_text(config_file.read_text(), source_name=str(config_file)) == new_config


def test_put_settings_structured_rejects_wrong_version_without_touching_disk(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(VALID_CONFIG_JSON_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.put(
            "/api/settings/structured", json={"config": {"version": 1}})

    assert response.status_code == 400
    assert config_file.read_text() == VALID_CONFIG_JSON_TEXT


def test_put_settings_structured_rejects_a_non_json_config_path(tmp_path):
    """The Form editor only ever writes JSON -- saving it against a
    server currently using a .toml config must be refused (pointing at
    Raw TOML or 'Load a different file' instead), not silently write
    JSON content into a .toml-named file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.put(
            "/api/settings/structured",
            json={"config": {"version": 3, "gui": {"x_column": "time", "axes": []}}})

    assert response.status_code == 400
    assert ".json" in response.json()["detail"]
    assert config_file.read_text() == VALID_CONFIG_TEXT


def test_load_settings_switches_the_active_config_path(tmp_path):
    original = tmp_path / "config.toml"
    original.write_text(VALID_CONFIG_TEXT)
    other = tmp_path / "other.toml"
    other.write_text(VALID_CONFIG_TEXT.replace('"t"', '"time"'))
    app = create_app({"x_column": "t", "axes": []}, config_path=str(original))

    with TestClient(app) as client:
        response = client.post("/api/settings/load", json={"path": str(other)})
        settings_after = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["path"] == str(other)
    # Switched, not just returned: a later GET /api/settings now reads
    # the newly loaded path, not the one the server originally started with.
    assert settings_after.json()["path"] == str(other)


def test_load_settings_rejects_a_missing_file_without_switching(tmp_path):
    original = tmp_path / "config.toml"
    original.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(original))

    with TestClient(app) as client:
        response = client.post(
            "/api/settings/load", json={"path": str(tmp_path / "missing.toml")})
        settings_after = client.get("/api/settings")

    assert response.status_code == 400
    assert settings_after.json()["path"] == str(original)


def test_restart_without_a_callback_reports_unsupported(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    with TestClient(app) as client:
        response = client.post("/api/settings/restart")

    assert response.status_code == 400


def test_restart_calls_the_callback_and_updates_gui_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))
    calls = []

    def fake_restart(path):
        calls.append(path)
        return {"x_column": "new_t", "axes": []}

    app.state.restart_callback = fake_restart

    with TestClient(app) as client:
        with client.websocket_connect("/ws/data") as ws:
            response = client.post("/api/settings/restart")
            message = ws.receive_json()
        config_after = client.get("/api/config")

    assert response.status_code == 200
    assert calls == [str(config_file)]
    assert config_after.json() == {"x_column": "new_t", "axes": []}
    # Connected chart tabs are told to reload, since axes/columns may
    # have changed shape.
    assert message == {"__aves_config_changed__": True}


def test_restart_reports_callback_errors_without_crashing(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file))

    def failing_restart(path):
        raise RuntimeError("serial port is on fire")

    app.state.restart_callback = failing_restart

    with TestClient(app) as client:
        response = client.post("/api/settings/restart")

    assert response.status_code == 400
    assert "serial port is on fire" in response.json()["detail"]


TOKEN = "s3cr3t-token"


def test_no_token_configured_leaves_everything_open():
    app = create_app({"x_column": "t", "axes": []})

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 200


def test_index_rejects_missing_or_wrong_token():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        no_token = client.get("/")
        wrong_token = client.get("/", params={"token": "nope"})

    assert no_token.status_code == 401
    assert wrong_token.status_code == 401


def test_index_html_path_also_requires_the_token():
    """A direct request for /index.html (not just "/") must not fall
    through to the unauthenticated static file mount -- that file
    genuinely exists in STATIC_DIR."""
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get("/index.html")

    assert response.status_code == 401


def test_settings_html_path_also_requires_the_token():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get("/settings.html")

    assert response.status_code == 401


def test_index_with_correct_query_token_serves_page_embeds_it_and_sets_cookie():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get("/", params={"token": TOKEN})

    assert response.status_code == 200
    assert f'"{TOKEN}"' in response.text
    assert "aves_token" in response.cookies
    assert response.cookies["aves_token"] == TOKEN


def test_index_with_valid_cookie_serves_page_without_query_token():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        client.get("/", params={"token": TOKEN})  # sets the cookie
        response = client.get("/")  # no ?token= this time

    assert response.status_code == 200


def test_api_config_rejects_missing_token():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 401


def test_api_config_accepts_authorization_header():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get(
            "/api/config", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200


def test_api_config_rejects_wrong_authorization_header():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        response = client.get(
            "/api/config", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_api_config_accepts_the_session_cookie():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        client.get("/", params={"token": TOKEN})  # sets the cookie
        response = client.get("/api/config")

    assert response.status_code == 200


def test_api_settings_requires_token(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file), token=TOKEN)

    with TestClient(app) as client:
        no_auth = client.get("/api/settings")
        with_auth = client.get(
            "/api/settings", headers={"Authorization": f"Bearer {TOKEN}"})

    assert no_auth.status_code == 401
    assert with_auth.status_code == 200


def test_api_settings_structured_requires_token(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(VALID_CONFIG_TEXT)
    app = create_app({"x_column": "t", "axes": []}, config_path=str(config_file), token=TOKEN)

    with TestClient(app) as client:
        no_auth = client.get("/api/settings/structured")
        with_auth = client.get(
            "/api/settings/structured", headers={"Authorization": f"Bearer {TOKEN}"})

    assert no_auth.status_code == 401
    assert with_auth.status_code == 200


def test_static_assets_do_not_require_a_token():
    """app.js/settings.js/style.css/vendor/* are just code, nothing
    sensitive -- only the two rendered HTML pages and the API are gated."""
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        app_js = client.get("/app.js")

    assert app_js.status_code == 200


def test_websocket_rejects_connection_without_token():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/data"):
                pass


def test_websocket_accepts_connection_with_query_token():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/data?token={TOKEN}") as ws:
            app.state.broadcaster.publish({"value": 1})
            assert ws.receive_json() == {"value": 1}


def test_websocket_accepts_connection_with_session_cookie():
    app = create_app({"x_column": "t", "axes": []}, token=TOKEN)

    with TestClient(app) as client:
        client.get("/", params={"token": TOKEN})  # sets the cookie
        with client.websocket_connect("/ws/data") as ws:
            app.state.broadcaster.publish({"value": 2})
            assert ws.receive_json() == {"value": 2}
