# -*- coding: utf-8 -*-
import errno
import os
import yaml


def mkdir_p(path):
    "Creates a directory, recursively if necessary"
    if path == "":
        return
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def parse_config(config_file="config.yaml"):
    if config_file.endswith("json"):
        raise ValueError("Please use aves < 3.0.0")
    with open(config_file) as stream:
        data = yaml.safe_load(stream)
    if data["version"] != 2:
        raise ValueError(
            "Don't know how to handle config.yaml with version != 2")
    return data
