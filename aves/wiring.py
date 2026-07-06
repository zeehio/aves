# -*- coding: utf-8 -*-
"""
Builds the io.py objects an acquisition run needs (input device, output
device) from plain values and a parsed config -- no argparse.Namespace,
no CLI assumptions. Shared by aves.realtime today, and meant to be
reused by any future entry point (e.g. a web backend) that needs the
same "port + config -> idev/outfile" wiring without depending on how
that entry point parses its own arguments.
"""

import os

from aves import io
from aves.utils import require_keys


def build_input_device(port, config, config_file="config.toml"):
    """
    Reads from the serial port, or replays a previously recorded file if
    ``port`` happens to be an existing file path.

    Args:
        port (str): Serial port name, or a path to a previously recorded
            file to replay.
        config (dict): Parsed config (see aves.utils.parse_config).
        config_file (str): Only used to name the file in error messages.
    """
    if os.path.isfile(port):
        require_keys(
            config, ["output"],
            f"{config_file} (its 'output' section describes the "
            "columns of the recorded file being replayed as input)")
        return io.ReadSensorFile(filename=port, config=config["output"])
    require_keys(
        config, ["input"],
        f"{config_file} (needed to read live from the serial port)")
    return io.ReadSensorSerial(port=port, config=config["input"])


def build_output_device(outfile, config):
    """Returns a WriteSensorFile, or None if the config has no output section."""
    if "output" not in config:
        return None
    return io.WriteSensorFile(filename=outfile, config=config["output"])
