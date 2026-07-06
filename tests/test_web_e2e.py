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
    """Runs a real aves.web app with uvicorn on a real port, in a
    background thread, so an actual browser can connect to it."""

    def __init__(self, gui_config):
        self.port = _free_port()
        self.app = create_app(gui_config)
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
                urllib.request.urlopen(f"{self.url}/api/config", timeout=0.2)
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
    with LiveServer(GUI_CONFIG) as server:
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
    with LiveServer(GUI_CONFIG) as server:
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

    with LiveServer(GUI_CONFIG) as server:
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
