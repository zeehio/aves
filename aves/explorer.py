# -*- coding: utf-8 -*-
"""
Created on Wed Aug 19 02:24:11 2015

@author: Sergio Oller

This module can be run as a program to visualize data acquired with aves.
It does two things:

 - It parses command line arguments. See: python3 -m aves.explorer --help
 - It runs the data visualization program:
     * It sets up the Graphical User Interface (GUI)
     * It opens the input file
     * Reads all samples
     * Optionally applies a median filter
     * Generates a plot with all the data
     * Waits until the user closes the window.
"""

# Make python2 use print as a function (py3 compatibility)
from __future__ import print_function

import argparse

from aves import gui
from aves import io
from aves import parse_config

def parse_arguments():
    """
    Parses command line arguments
    """
    parser = argparse.ArgumentParser(description="Analysis of Arduino sensors")
    # add expected arguments
    parser.add_argument("--filename", dest='filename', default=None,
                        help="file name to load")
    parser.add_argument('--config', dest='config_file', default='config.json',
                        help="Arduino output columns, GUI layout and file format")
    # parse args
    args = parser.parse_args()
    # If no filename is given, show a dialog to load one
    if args.filename is None:
        args.filename = gui.filename_from_dialog(path="data")
    # Uncomment to debug the output of argparse:
    # raise ValueError(args)
    return args


def DataExplorer():
    """ Main function: Sets up the GUI and takes care of
    the main loop of the script
    """
    # create parser
    args = parse_arguments()
    # Parse config (plot layout and description of arduino output)
    config = parse_config(config_file=args.config_file)
    window = gui.SensorViewerGUI(config=config["gui"])
    time_python = config["input"]["time_python"]
    x_axis_data = config["gui"]["x_points"]
    with io.ReadSensorFile(filename=args.filename, config=config["output"]) as idev:
        samples = idev.readsamples()
    # Add samples to buffers
    buffers = io.DataBuffers(maxlen=len(samples))
    buffers.extend(samples)
    # Copy buffer to gui
    if buffers.data:
        window.set_data(buffers.data)
        # Update limits on the x axis in the GUI:
        window.set_xlim()
        window.update()
    window.wait_until_close()

if __name__ == '__main__':
    DataExplorer()

