# -*- coding: utf-8 -*-
"""
Created on Wed Aug 19 02:24:11 2015

@author: Sergio Oller

This module can be run as a program to acquire data and visualize it on real time.

It does two things:

 - It parses command line arguments. See: python3 -m aves.realtime --help
 - It runs the acquisition program:
     * It sets up the Graphical User Interface (GUI), if configured
     * It opens the serial port
     * It drives a loop that reads a batch of samples, writes them to a
       file, buffers them, and (if there is a GUI) renders them, until
       the experiment duration is reached, the input runs out, or the
       user closes the window.
"""

import os
import datetime
import argparse
import contextlib

from aves import gui
from aves import io
from aves.acquisition import Acquisition
from aves.utils import parse_config
from aves.wiring import build_input_device, build_output_device


def _parse_arguments():
    """
    Parses command line arguments
    """
    fname_new = datetime.datetime.now().strftime("%Y_%m_%d-%H.%M.%S.txt")
    fname_new = os.path.join("data", fname_new)
    parser = argparse.ArgumentParser(description="Read Arduino sensors")
    # add expected arguments
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
                        help="samples to collect before plotting (default:10)")
    parser.add_argument('--plot_win_size', dest='plot_win_size',
                        type=int, default=200,
                        help="keeps in the plot the given number of samples " +
                             "(default:200 samples, use 0 for unlimited)""")
    parser.add_argument('--config', dest='config_file', default='config.toml',
                        help="Arduino output columns, GUI layout and file format")

    # parse args
    args = parser.parse_args()
    if not args.save:
        args.outfile = None
    if args.plot_win_size == 0:
        args.plot_win_size = None
    # Uncomment to debug the output of argparse:
    # raise ValueError(args)
    return args


class RealTimeAnalysis(object):
    def __init__(self):
        # Parse input arguments, show help...
        self.args = _parse_arguments()
        # Parse config (plot layout and description of arduino output)
        config = parse_config(config_file=self.args.config_file)
        # Buffers with the data to be plotted on each instant are saved here:
        buffers = io.DataBuffers(maxlen=self.args.plot_win_size)
        # Use the Serial port or mock the serial port with a file:
        idev = build_input_device(
            self.args.port, config, config_file=self.args.config_file)
        outfile = build_output_device(self.args.outfile, config)
        # Create the figure, axis and the GUI:
        self.window = gui.SensorViewerGUI(config=config["gui"]) if "gui" in config else None

        outfile_ctx = outfile if outfile is not None else contextlib.nullcontext()
        # With clause makes sure the serial port and output file are always properly closed
        with idev, outfile_ctx:
            self.acquisition = Acquisition(
                idev=idev, buffers=buffers, outfile=outfile,
                tmeas=self.args.tmeas,
                samples_per_step=self.args.plot_every_n_samples)
            self._run()

    def _tick(self):
        """
        Reads/writes/buffers one batch of samples, renders it (if there is
        a GUI), and returns whether acquisition should keep going.
        """
        self.acquisition.step()
        if self.window is not None and self.acquisition.buffers.data:
            self.window.render(self.acquisition.buffers.data)
        window_closed = self.window is not None and self.window.closed
        return not (self.acquisition.should_stop() or window_closed)

    def _run(self):
        if self.window is None:
            while self._tick():
                pass
        else:
            self.window.run(self._tick)


if __name__ == '__main__':
    RealTimeAnalysis()
