from fastapi.testclient import TestClient

from aves.web.server import create_app

VALID_CONFIG_TEXT = 'version = 3\n\n[gui]\nx_column = "t"\naxes = []\n'


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
