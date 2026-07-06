from fastapi.testclient import TestClient

from aves.web.server import create_app


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
