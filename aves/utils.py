# -*- coding: utf-8 -*-
import errno
import os
import tomllib


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


def require_keys(mapping, keys, name):
    """
    Ensures ``mapping`` is a dict containing every key in ``keys``, raising
    a clear ``ValueError`` (naming ``name`` and the missing keys) instead of
    a bare ``KeyError`` deep inside whatever reads the missing key next.

    Returns ``mapping`` unchanged, so this can be used inline:

        arduino = require_keys(config, ["arduino"], "...")["arduino"]
    """
    if not isinstance(mapping, dict):
        raise ValueError(f"{name} must be a mapping, got {type(mapping).__name__}")
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValueError(f"{name} is missing required key(s): {', '.join(missing)}")
    return mapping


def parse_config(config_file="config.toml"):
    if config_file.endswith("json"):
        raise ValueError("Please use aves < 3.0.0")
    if config_file.endswith((".yaml", ".yml")):
        raise ValueError(
            f"{config_file} looks like a YAML file. Since aves 4.0.0, "
            "config files use TOML (config.toml) instead. Please convert "
            "it -- see the README for the new schema.")
    with open(config_file, "rb") as stream:
        try:
            data = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"Could not parse {config_file} as TOML: {exc}") from exc
    if "version" not in data:
        raise ValueError(
            f"{config_file} is missing the required 'version' key "
            "(expected version = 3)")
    if data["version"] != 3:
        raise ValueError(
            f"{config_file} has version {data['version']!r}, but this "
            "version of aves only supports config files with version = 3")
    return data
