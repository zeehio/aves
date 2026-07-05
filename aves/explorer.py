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

import argparse

from aves import gui
from aves import io
from aves.utils import parse_config, require_keys


def parse_arguments():
    """
    Parses command line arguments
    """
    parser = argparse.ArgumentParser(description="Analysis of Arduino sensors")
    # add expected arguments
    parser.add_argument("--filename", dest='filename', default=None,
                        help="file name to load")
    parser.add_argument('--config', dest='config_file', default='config.yaml',
                        help="Arduino columns, GUI layout and file format")
    # parse args
    args = parser.parse_args()
    # If no filename is given, show a dialog to load one. Only needed as a
    # fallback when --filename is omitted, so this stays a local import: it's
    # the only thing in this module that needs Tk installed (SensorViewerGUI
    # itself only needs matplotlib).
    if args.filename is None:
        from aves import dialogs
        args.filename = dialogs.filename_from_dialog(path="data")
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
    require_keys(config, ["gui", "output"], "config.yaml")
    window = gui.SensorViewerGUI(config=config["gui"])
    with io.ReadSensorFile(filename=args.filename, config=config["output"]) as idev:
        samples = idev.readsamples()
    # Add samples to buffers
    buffers = io.DataBuffers(maxlen=len(samples))
    buffers.extend(samples)
    # Copy buffer to gui
    if buffers.data:
        window.render(buffers.data)
    window.wait_until_close()


if __name__ == '__main__':
    DataExplorer()
