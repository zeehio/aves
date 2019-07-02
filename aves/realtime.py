# -*- coding: utf-8 -*-
"""
Created on Wed Aug 19 02:24:11 2015

@author: Sergio Oller

This module can be run as a program to acquire data and visualize it on real time.

It does two things:

 - It parses command line arguments. See: python3 -m aves.realtime --help
 - It runs the acquisition program:
     * It sets up the Graphical User Interface (GUI)
     * It opens the serial port
     * While there is data to read and the window is open and the experiment
       duration has not reached a limit, it acquires a sample and adds it to
       the plot, updating it.
"""

# Make python2 use print as a function (for python3 compatibility)
from __future__ import print_function

import os
import datetime
import argparse
from functools import partial

from aves import gui
from aves import io
from aves import parse_config

def _parse_arguments():
    """
    Parses command line arguments
    """
    fname_new = datetime.datetime.now().strftime("%Y_%m_%d-%H.%M.%S.txt")
    fname_new = os.path.join("data", fname_new)
    parser = argparse.ArgumentParser(description="Read Arduino sensors")
    # add expected arguments
    parser.add_argument('--port', dest='port', default='COM5',
                        help="serial port to read data from")
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
    parser.add_argument('--config', dest='config_file', default='config.yaml',
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
    def  __init__(self):
        # Parse input arguments, show help...
        self.args = _parse_arguments()
        # Parse config (plot layout and description of arduino output)
        config = parse_config(config_file=self.args.config_file)
        # Measure current time:
        self.start = datetime.datetime.now()
        # Buffers with the data to be plotted on each instant are saved here:
        self.buffers = io.DataBuffers(maxlen=self.args.plot_win_size)
        # Use the Serial port or mock the serial port with a file:
        if os.path.isfile(self.args.port):
            input_dev = partial(io.ReadSensorFile, filename=self.args.port, config=config["output"])
        else:
            input_dev = partial(io.ReadSensorSerial, port=self.args.port, config=config["input"])
        # Create the figure, axis and the GUI:
        if "gui" in config.keys():
            self.window = gui.SensorViewerGUI(config=config["gui"])
        else:
            self.window = None
        if "output" in config.keys():
            output_dev = partial(io.WriteSensorFile, filename=self.args.outfile, config=config["output"])
        else:
            output_dev = lambda: None
        # With clause makes sure serial port is always properly closed
        with input_dev() as self.idev, output_dev() as self.outfile:
            if self.window is None:
                self.while_loop()
            else:
                self.window.while_loop(stop_condition = self.stop_condition, loop = self.loop)

    def while_loop(self):
        while not self.stop_condition():
            self.loop()

    def stop_condition(self):
        # Stop conditions:
        #  - We have been measuring for more than tmeas seconds OR
        #  - We have a GUI and we close the window OR
        #  - The input device has stopped reading
        return ((datetime.datetime.now()-self.start).total_seconds() > self.args.tmeas or
            (self.window is not None and self.window.stop_sampling) or
            self.idev.stop_sampling)

    def loop(self):
        # The GUI is updated every N samples. Read N consecutive samples
        samples = self.idev.readsamples(num_samples=self.args.plot_every_n_samples)
        # Write samples to file
        if self.outfile is not None:
            self.outfile.write(samples)
        # Add samples to buffers
        self.buffers.extendleft(samples)
        if self.buffers.data and self.window is not None:
            # Copy buffer to gui
            self.window.set_data(self.buffers.data)
            # Update limits on the x axis in the GUI:
            self.window.set_xlim()
        return


if __name__ == '__main__':
    RealTimeAnalysis()

