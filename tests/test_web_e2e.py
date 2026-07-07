# -*- coding: utf-8 -*-
"""
End-to-end tests driving a real browser (via Playwright) against a real
aves.web server bound to a real TCP port. FastAPI's TestClient (used in
test_web_server.py) only works in-process; it can't be driven by an actual
browser, which is a separate process talking real HTTP/WebSocket.

These tests use a synthetic publisher paced like a real, rate-limited
sensor (a small time.sleep between publishes), not an unthrottled file
replay: a fast, unthrottled producer races the browser's ability to even
subscribe before all the data is gone, and can flood the broadcaster's
per-client queue faster than any consumer can drain it. Neither of those
is what these tests are trying to measure.
"""

import math
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from aves.web.server import create_app

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

#: Set by CI (after `playwright install chromium`) if the browser isn't on
#: Playwright's default lookup path; unset locally uses Playwright's own.
CHROMIUM_EXECUTABLE = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None

GUI_CONFIG = {
    "x_column": "time_arduino",
    "zoom_all_together": True,
    "axes": [
        {"name": "Sensor 1", "row": 0, "col": 0, "columns": ["Sensor 1"],
         "ylim": [-0.5, 5.5], "ylabel": "Sensor 1 (V)"},
    ],
}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    """Runs a real aves.web app (built by the caller, via create_app or
    aves.web.__main__.main's own setup) with uvicorn on a real port, in a
    background thread, so an actual browser can connect to it."""

    def __init__(self, app):
        self.port = _free_port()
        self.app = app
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                # Any HTTP response (even a 401, e.g. when a token is
                # configured) means the server is up and routing requests.
                urllib.request.urlopen(f"{self.url}/api/config", timeout=0.2)
                return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("aves.web server did not start in time")

    def __exit__(self, *exc_info):
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _publish_synthetic_samples(broadcaster, n_messages, interval, maxlen):
    """Publishes n_messages batches, each carrying its own wall-clock
    publish time, at a controlled pace."""
    times, values = [], []
    for i in range(n_messages):
        times.append(i * 0.01)
        values.append(2.5 + 1.5 * math.sin(i / 20.0))
        times, values = times[-maxlen:], values[-maxlen:]
        broadcaster.publish({
            "time_arduino": list(times),
            "Sensor 1": list(values),
            "_test_published_at": time.time(),
        })
        if interval:
            time.sleep(interval)


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROMIUM_EXECUTABLE)
        browser_page = browser.new_page()
        yield browser_page
        browser.close()


def test_latency_from_sample_publish_to_on_screen_render(page):
    """Measures wall-clock time from "a sample was published" to "the
    browser finished drawing it", end to end through the real WebSocket
    and the real app.js rendering path (not just message arrival)."""
    with LiveServer(create_app(GUI_CONFIG)) as server:
        page.goto(server.url)
        page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        page.evaluate("""
        () => {
            window.__latenciesMs = [];
            window.addEventListener("aves:data-rendered", (e) => {
                const publishedAt = e.detail.data._test_published_at;
                if (typeof publishedAt === "number") {
                    window.__latenciesMs.push(Date.now() - publishedAt * 1000);
                }
            });
        }
        """)

        _publish_synthetic_samples(
            server.app.state.broadcaster, n_messages=40, interval=0.05, maxlen=50)

        page.wait_for_function("window.__latenciesMs.length >= 30", timeout=5000)
        latencies_ms = page.evaluate("window.__latenciesMs")

    assert len(latencies_ms) >= 30
    # Same-machine localhost WebSocket: should be near-instant. Bound left
    # generous on purpose to absorb CI scheduling jitter, not tuned as a
    # tight performance assertion.
    mean_latency = sum(latencies_ms) / len(latencies_ms)
    assert mean_latency < 200, f"mean latency {mean_latency}ms too high: {latencies_ms}"
    assert max(latencies_ms) < 1000, f"latency spike too high: {latencies_ms}"


def test_browser_keeps_only_the_current_window_not_full_history(page):
    """The server already windows samples (aves.io.DataBuffers(maxlen=...))
    and re-publishes the whole current window each time, not deltas -- so
    the frontend must replace its chart data wholesale on each message,
    never accumulate it. This proves that structurally: after streaming far
    more samples than the window holds, each chart's retained data must
    still be capped at the window size, not the total sample count."""
    maxlen = 50
    n_messages = 2000
    with LiveServer(create_app(GUI_CONFIG)) as server:
        page.goto(server.url)
        page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        _publish_synthetic_samples(
            server.app.state.broadcaster, n_messages=n_messages, interval=0,
            maxlen=maxlen)

        page.wait_for_function(
            f"window.__avesRenderCount >= {n_messages}", timeout=5000)
        chart_data_lengths = page.evaluate(
            "window.__avesCharts.map(c => c.plot.data[0].length)")

    assert chart_data_lengths
    for length in chart_data_lengths:
        assert length <= maxlen, (
            f"chart retained {length} points after {n_messages} samples "
            f"streamed (window size is {maxlen}) -- looks like it's "
            f"accumulating instead of replacing")


def test_browser_memory_stays_bounded_under_sustained_streaming(page):
    """Best-effort RAM-stability check: stream far more messages than the
    window can hold, in two halves, forcing a GC and sampling the JS heap
    between them. If the frontend leaked retained data per message, heap
    usage would keep climbing with total messages seen; since it only ever
    holds the current window, heap usage after warm-up should plateau."""
    maxlen = 50
    n_messages_per_half = 3000

    with LiveServer(create_app(GUI_CONFIG)) as server:
        page.goto(server.url)
        page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        cdp = page.context.new_cdp_session(page)

        def heap_bytes_after_gc():
            cdp.send("HeapProfiler.collectGarbage")
            return page.evaluate(
                "window.performance.memory ? "
                "window.performance.memory.usedJSHeapSize : null")

        # Warm-up: let allocation patterns settle before the baseline. Each
        # half must be fully rendered (not just published/queued) before
        # measuring, or the heap sample would race the browser's processing.
        _publish_synthetic_samples(
            server.app.state.broadcaster, n_messages_per_half, 0, maxlen)
        page.wait_for_function(
            f"window.__avesRenderCount >= {n_messages_per_half}", timeout=10000)
        baseline_heap = heap_bytes_after_gc()

        _publish_synthetic_samples(
            server.app.state.broadcaster, n_messages_per_half, 0, maxlen)
        page.wait_for_function(
            f"window.__avesRenderCount >= {2 * n_messages_per_half}", timeout=10000)
        after_heap = heap_bytes_after_gc()

    if baseline_heap is None or after_heap is None:
        pytest.skip("performance.memory is not available in this browser")

    assert baseline_heap > 0
    growth_ratio = after_heap / baseline_heap
    assert growth_ratio < 1.5, (
        f"JS heap grew {growth_ratio:.2f}x ({baseline_heap} -> {after_heap} "
        f"bytes) after {n_messages_per_half} more messages past warm-up -- "
        f"looks like the frontend is retaining data instead of replacing it")


def _make_settings_app(tmp_path, window_title="Before", token=None, config_format="toml"):
    """Builds a real app wired for /api/settings/restart the same way
    aves.web.__main__.main() does, backed by a real config file and a
    real (tiny) file replay, so restart genuinely stops and rebuilds an
    Acquisition rather than faking it."""
    import json
    import types

    from aves.utils import parse_config
    from aves.web.__main__ import AcquisitionManager

    config_file = tmp_path / f"config.{config_format}"
    if config_format == "json":
        config_file.write_text(json.dumps({
            "version": 3,
            "gui": {
                "x_column": "t", "zoom_all_together": True,
                "window_title": window_title, "axes": [],
            },
            "output": {"columns": ["t"]},
        }))
    else:
        config_file.write_text(
            "version = 3\n\n"
            "[gui]\n"
            'x_column = "t"\n'
            "zoom_all_together = true\n"
            f'window_title = "{window_title}"\n'
            "axes = []\n\n"
            "[output]\n"
            'columns = ["t"]\n')
    infile = tmp_path / "in.txt"
    infile.write_text("0\n1\n2\n")

    initial_config = parse_config(config_file=str(config_file))
    app = create_app(initial_config["gui"], config_path=str(config_file), token=token)
    args = types.SimpleNamespace(
        port=str(infile), config_file=str(config_file), outfile=None,
        plot_win_size=200, tmeas=float("inf"), plot_every_n_samples=1)
    manager = AcquisitionManager(app, args)
    app.state.restart_callback = manager.restart
    manager.start(initial_config)
    return app, config_file


def test_settings_form_previews_layout_and_input_conversion(page, tmp_path):
    """The settings page's live previews: a grid box per axis (placed by
    row/col/rowspan/colspan, one fake series line per plotted column) and
    an input-conversion table (raw example value times conversion_factor).
    Both must track edits without requiring a save/reload round trip."""
    import json

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "version": 3,
        "input": {"arduino": {"baudrate": 9600, "timeout": 3, "columns": [
            {"name": "time_arduino", "conversion_factor": 0.001},
            {"name": "Sensor 1", "conversion_factor": 0.004887586},
        ]}},
        "gui": {
            "x_column": "time_arduino", "zoom_all_together": True,
            "axes": [
                {"name": "Sensor 1", "row": 0, "col": 0, "columns": ["Sensor 1"],
                 "ylabel": "Sensor 1 (V)", "title": "Sensor 1 readings"},
                {"name": "Empty", "row": 0, "col": 1, "columns": []},
            ],
        },
        "output": {"columns": ["time_computer", "time_arduino", "Sensor 1"]},
    }))
    app = create_app({}, config_path=str(config_file))

    with LiveServer(app) as server:
        page.goto(f"{server.url}/settings.html")
        page.wait_for_function(
            "document.getElementById('status').textContent.startsWith('Loaded')",
            timeout=5000)

        # One preview box per axis, placed in the right grid cell, with a
        # fake series line for the plotted axis and a "no columns" message
        # for the empty one -- not just a raw dump of the axes array.
        boxes = page.locator(".axis-preview-box")
        assert boxes.count() == 2
        assert "Sensor 1 readings" in boxes.nth(0).inner_text()
        assert boxes.nth(0).locator(".axis-preview-svg polyline").count() == 1
        assert "no columns" in boxes.nth(1).inner_text()

        # Editing the conversion factor updates the input-preview table
        # live, with no save/reload needed.
        factor_input = page.locator(
            "#input-fields table.rows-table:not(.preview-table) tbody tr"
        ).nth(1).locator("input[type=number]")
        factor_input.fill("2")
        factor_input.dispatch_event("change")
        preview_text = page.locator("#input-fields .preview-table").inner_text()
        assert "Sensor 1\t1000\t× 2\t= 2000" in preview_text

        # Moving axis 1 to a new row/col relocates its preview box, and
        # adding a second column to it adds a second fake series line.
        axis1 = page.locator(".axis-box").nth(0)
        axis1.get_by_label("Row", exact=True).fill("1")
        axis1.get_by_label("Row", exact=True).blur()
        axis1.locator(".column-checkbox", has_text="time_arduino").locator("input").check()
        page.wait_for_timeout(100)

        moved_box = page.locator(".axis-preview-box").nth(0)
        assert moved_box.evaluate("el => el.style.gridRow") == "2 / span 1"
        assert moved_box.locator(".axis-preview-svg polyline").count() == 2


def test_settings_form_edits_and_restarts_with_the_edited_config(page, tmp_path):
    """The settings page's form editor end-to-end: edit a field, save,
    restart, and see the change take effect. The form only ever writes
    JSON, so this needs a .json config file."""
    app, config_file = _make_settings_app(tmp_path, window_title="Before", config_format="json")

    with LiveServer(app) as server:
        page.goto(f"{server.url}/settings.html")
        page.wait_for_function(
            "document.getElementById('status').textContent.startsWith('Loaded')",
            timeout=5000)

        window_title_input = page.locator(
            "#gui-fields .field", has_text="Window title").locator("input")
        window_title_input.fill("After")
        window_title_input.blur()
        page.click("#restart-btn")

        page.wait_for_url(f"{server.url}/", timeout=5000)
        page.wait_for_function("document.title === 'After'", timeout=5000)

    import json
    assert json.loads(config_file.read_text())["gui"]["window_title"] == "After"


def test_settings_changes_reload_other_already_open_chart_tabs(page, tmp_path):
    """A restart from the settings page must refresh every open chart
    tab, not just the one used to trigger it -- otherwise a second tab
    would keep rendering against stale axes/columns."""
    app, config_file = _make_settings_app(tmp_path, window_title="Before", config_format="json")

    with LiveServer(app) as server:
        chart_page = page
        chart_page.goto(server.url)
        chart_page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        # A separate browser context (not chart_page.context.new_page(),
        # which Playwright disallows for a context created via the
        # browser.new_page() shortcut) -- the config-changed broadcast is
        # server-side and reaches every connected client regardless.
        settings_page = chart_page.context.browser.new_page()
        settings_page.goto(f"{server.url}/settings.html")
        settings_page.wait_for_function(
            "document.getElementById('status').textContent.startsWith('Loaded')",
            timeout=5000)
        window_title_input = settings_page.locator(
            "#gui-fields .field", has_text="Window title").locator("input")
        window_title_input.fill("Bystander")
        window_title_input.blur()
        settings_page.click("#restart-btn")
        settings_page.wait_for_url(f"{server.url}/", timeout=5000)

        # chart_page never clicked anything.
        chart_page.wait_for_function("document.title === 'Bystander'", timeout=5000)
        settings_page.close()


def test_settings_save_disabled_for_a_toml_config_with_a_clear_hint(page, tmp_path):
    """The form only ever writes JSON, so pointed at a .toml config it
    must not offer a Save/Restart that would just fail (or, worse,
    silently corrupt the file) -- it should disable both and tell the
    user to use a text editor or point at a .json config instead."""
    app, config_file = _make_settings_app(tmp_path, window_title="Before", config_format="toml")
    original_text = config_file.read_text()

    with LiveServer(app) as server:
        page.goto(f"{server.url}/settings.html")
        page.wait_for_function(
            "document.getElementById('status').textContent.startsWith('Loaded')",
            timeout=5000)

        assert page.is_disabled("#save-btn")
        assert page.is_disabled("#restart-btn")
        status_text = page.text_content("#status")

    assert "text editor" in status_text
    assert config_file.read_text() == original_text


TOKEN = "e2e-test-token"


def test_token_blocks_access_without_it_and_a_valid_link_gets_you_in(page):
    with LiveServer(create_app(GUI_CONFIG, token=TOKEN)) as server:
        rejected = page.goto(server.url)
        assert rejected.status == 401

        page.goto(f"{server.url}/?token={TOKEN}")
        page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        cookies = page.context.cookies()
        assert any(c["name"] == "aves_token" and c["value"] == TOKEN for c in cookies)


def test_token_cookie_carries_over_to_a_plain_link_navigation(page):
    """Clicking the Settings link (a plain <a href>, no token in the URL)
    must still work after the initial token-authenticated visit. GUI_CONFIG
    has no config_path, so /api/settings 404s ("no config file") rather
    than loading -- what this checks is that it isn't a 401 (i.e. the
    cookie, not the missing config, is why there's nothing to show)."""
    with LiveServer(create_app(GUI_CONFIG, token=TOKEN)) as server:
        page.goto(f"{server.url}/?token={TOKEN}")
        page.wait_for_function(
            "document.getElementById('status').textContent === 'connected'",
            timeout=5000)

        page.click("text=Settings")
        page.wait_for_url(f"{server.url}/settings.html", timeout=5000)
        page.wait_for_function(
            "document.getElementById('status').textContent !== 'loading…'",
            timeout=5000)
        status_text = page.text_content("#status")

    assert "missing or invalid token" not in status_text


def test_settings_save_and_restart_work_with_a_token_configured(page, tmp_path):
    app, config_file = _make_settings_app(
        tmp_path, window_title="Before", token=TOKEN, config_format="json")

    with LiveServer(app) as server:
        page.goto(f"{server.url}/settings.html?token={TOKEN}")
        page.wait_for_function(
            "document.getElementById('status').textContent.startsWith('Loaded')",
            timeout=5000)

        window_title_input = page.locator(
            "#gui-fields .field", has_text="Window title").locator("input")
        window_title_input.fill("After")
        window_title_input.blur()
        page.click("#restart-btn")

        page.wait_for_url(f"{server.url}/", timeout=5000)
        page.wait_for_function("document.title === 'After'", timeout=5000)

    import json
    assert json.loads(config_file.read_text())["gui"]["window_title"] == "After"
