# -*- coding: utf-8 -*-
"""
Runs a small local web server that acquires data exactly like
aves.realtime, but streams it to a browser (aves/web/server.py) instead
of a matplotlib window. Acquisition runs in a background thread; the
web server owns the main thread. Neither one is aware of the other
beyond the Broadcaster: acquisition calls broadcaster.publish(data)
after each batch, same "here is the data, render it however" boundary
aves.gui.SensorViewerGUI.render() already uses.

    python3 -m aves.web --port ... [--host 127.0.0.1] [--web-port 8000]

The server binds to 127.0.0.1 by default: this is meant to be viewed
from a browser on the same machine, not exposed on a network. It also
requires a random token by default (printed at startup as part of the
URL to open) -- see aves.web.server's module docstring for what that
does and doesn't protect against.
"""

import argparse
import contextlib
import datetime
import os
import secrets
import threading

import uvicorn

from aves import io
from aves.acquisition import Acquisition
from aves.utils import parse_config, require_keys
from aves.wiring import build_input_device, build_output_device
from aves.web.server import create_app

#: How long to wait for the acquisition thread to notice a stop request
#: and return, when stopping it for a restart. A blocked serial read only
#: gets checked between reads, so this must outlast the config's
#: input.arduino.timeout for a graceful stop to actually happen in time.
STOP_TIMEOUT_SECONDS = 10


def _parse_arguments():
    fname_new = datetime.datetime.now().strftime("%Y_%m_%d-%H.%M.%S.txt")
    fname_new = os.path.join("data", fname_new)
    parser = argparse.ArgumentParser(
        description="Read Arduino sensors, view them in a browser")
    parser.add_argument('--port', dest='port', required=True,
                        help="serial port to read data from (e.g. COM3 on "
                             "Windows, /dev/ttyUSB0 or /dev/ttyACM0 on "
                             "Linux, /dev/cu.usbmodemXXXX on macOS), or a "
                             "path to a previously recorded file to replay")
    parser.add_argument('--no-save', dest='save', action="store_false",
                        help="skip saving acquired data to a file")
    parser.add_argument('--time', dest='tmeas', default=float('inf'),
                        type=float,
                        help="duration of the experiment in seconds " +
                             "(default: unlimited)")
    parser.add_argument('--outfile', dest='outfile', default=fname_new,
                        help="file name to save the experiment into")
    parser.add_argument('--plot_every_n_samples', dest='plot_every_n_samples',
                        type=int, default=10,
                        help="samples to collect before publishing an "
                             "update to connected browsers (default:10)")
    parser.add_argument('--plot_win_size', dest='plot_win_size',
                        type=int, default=200,
                        help="keeps in memory the given number of samples " +
                             "(default:200 samples, use 0 for unlimited)")
    parser.add_argument('--config', dest='config_file', default='config.toml',
                        help="Arduino output columns, GUI layout and file format")
    parser.add_argument('--host', dest='host', default='127.0.0.1',
                        help="address to bind the local web server to " +
                             "(default: 127.0.0.1, this machine only)")
    parser.add_argument('--web-port', dest='web_port', type=int, default=8000,
                        help="TCP port for the local web server (default: 8000)")
    parser.add_argument('--token', dest='token', default=None,
                        help="require this token to access the web UI "
                             "(as ?token=... on first visit, then "
                             "Authorization: Bearer ... on API calls); "
                             "default: a fresh random token printed at "
                             "startup. Pass --token='' to disable -- only "
                             "for trusted, fully local use")

    args = parser.parse_args()
    if not args.save:
        args.outfile = None
    if args.plot_win_size == 0:
        args.plot_win_size = None
    return args


def _acquisition_loop(acquisition, broadcaster, stop_event):
    """
    Runs in a background thread. Waits for the server's event loop to
    exist (broadcaster.publish() needs it) before doing anything else.
    """
    broadcaster.ready.wait()
    while not stop_event.is_set():
        acquisition.step()
        if acquisition.buffers.data:
            broadcaster.publish(
                {name: list(values) for name, values in acquisition.buffers.data.items()})
        if acquisition.should_stop():
            break


class AcquisitionManager:
    """
    Owns the lifecycle of the *current* acquisition (the input device, the
    output file, and the background thread running _acquisition_loop), so
    it can be stopped and restarted -- e.g. after the config file was
    edited and saved through the web settings page -- without tearing down
    the web server (and its already-connected browsers) itself.

    Only one acquisition runs at a time. restart() does not roll back: if
    building the new one fails (bad serial port, missing config keys...),
    the old one has already been stopped, so no acquisition is running
    until the config is fixed and restart() is called again. That failure
    is reported back to the caller (surfaced to the browser as the
    restart's error message) rather than silently leaving stale state.
    """

    def __init__(self, app, args):
        self._app = app
        self._args = args
        self._lock = threading.Lock()
        self._stack = None
        self._thread = None
        self._stop_event = None

    @property
    def is_running(self):
        return self._thread is not None

    def start(self, config):
        with self._lock:
            if self._thread is not None:
                raise RuntimeError(
                    "an acquisition is already running; stop it first")
            require_keys(
                config, ["gui"], f"{self._args.config_file} (needed to run aves.web)")
            stack = contextlib.ExitStack()
            try:
                idev = build_input_device(
                    self._args.port, config, config_file=self._args.config_file)
                stack.enter_context(idev)
                outfile = build_output_device(self._args.outfile, config)
                if outfile is not None:
                    stack.enter_context(outfile)
            except Exception:
                stack.close()
                raise
            buffers = io.DataBuffers(maxlen=self._args.plot_win_size)
            acquisition = Acquisition(
                idev=idev, buffers=buffers, outfile=outfile,
                tmeas=self._args.tmeas, samples_per_step=self._args.plot_every_n_samples)
            stop_event = threading.Event()
            thread = threading.Thread(
                target=_acquisition_loop,
                args=(acquisition, self._app.state.broadcaster, stop_event),
                daemon=True)
            self._stack = stack
            self._stop_event = stop_event
            self._thread = thread
            self._app.state.gui_config = config["gui"]
            thread.start()

    def stop(self):
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=STOP_TIMEOUT_SECONDS)
            if self._thread.is_alive():
                raise RuntimeError(
                    f"acquisition did not stop within {STOP_TIMEOUT_SECONDS}s "
                    "-- is it blocked on a serial read? check the config's "
                    "input.arduino.timeout")
            self._stack.close()
            self._thread = None
            self._stop_event = None
            self._stack = None

    def restart(self, config_path=None):
        """
        Reloads the config from disk (config_path, or whatever path was
        used last), stops the current acquisition, and starts a new one
        from it. Meant to be called from a thread executor (it blocks on
        stop()), and returns the new gui config so the caller can update
        whatever it serves at GET /api/config.
        """
        path = config_path or self._args.config_file
        config = parse_config(config_file=path)
        self.stop()
        self._args.config_file = path
        self.start(config)
        return config["gui"]


def main():
    args = _parse_arguments()
    config = parse_config(config_file=args.config_file)
    require_keys(config, ["gui"], f"{args.config_file} (needed to run aves.web)")

    # Not passed at all -> a fresh random token; passed as '' -> disabled
    # (only meant for trusted, fully local use); passed as anything else
    # -> that fixed value (e.g. for scripting/reconnecting).
    token = secrets.token_urlsafe(32) if args.token is None else (args.token or None)

    app = create_app(config["gui"], config_path=args.config_file, token=token)
    manager = AcquisitionManager(app, args)
    app.state.restart_callback = manager.restart

    manager.start(config)
    url = f"http://{args.host}:{args.web_port}/"
    if token:
        print(f"Open {url}?token={token} to view the acquisition.")
    else:
        print(
            f"Open {url} to view the acquisition. Running with --token='': "
            "anyone who can reach this port can view data and read/write "
            "local files through it.")
    try:
        uvicorn.run(app, host=args.host, port=args.web_port)
    finally:
        manager.stop()


if __name__ == '__main__':
    main()
