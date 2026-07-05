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
        try:
            data = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ValueError(f"Could not parse {config_file} as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{config_file} must contain a YAML mapping with a top-level "
            "'version' key, 'input', 'gui' and 'output' sections")
    if "version" not in data:
        raise ValueError(
            f"{config_file} is missing the required 'version' key "
            "(expected version: 2)")
    if data["version"] != 2:
        raise ValueError(
            f"{config_file} has version {data['version']!r}, but this "
            "version of aves only supports config files with version: 2")
    return data
