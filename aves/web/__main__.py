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
from a browser on the same machine, not exposed on a network.
"""

import argparse
import contextlib
import datetime
import os
import threading

import uvicorn

from aves import io
from aves.acquisition import Acquisition
from aves.utils import parse_config, require_keys
from aves.wiring import build_input_device, build_output_device
from aves.web.server import create_app


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


def main():
    args = _parse_arguments()
    config = parse_config(config_file=args.config_file)
    require_keys(config, ["gui"], f"{args.config_file} (needed to run aves.web)")

    buffers = io.DataBuffers(maxlen=args.plot_win_size)
    idev = build_input_device(args.port, config, config_file=args.config_file)
    outfile = build_output_device(args.outfile, config)
    app = create_app(config["gui"])

    outfile_ctx = outfile if outfile is not None else contextlib.nullcontext()
    # With clause makes sure the serial port and output file are always properly closed
    with idev, outfile_ctx:
        acquisition = Acquisition(
            idev=idev, buffers=buffers, outfile=outfile,
            tmeas=args.tmeas, samples_per_step=args.plot_every_n_samples)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_acquisition_loop,
            args=(acquisition, app.state.broadcaster, stop_event),
            daemon=True)
        thread.start()
        try:
            uvicorn.run(app, host=args.host, port=args.web_port)
        finally:
            stop_event.set()
            thread.join()


if __name__ == '__main__':
    main()
