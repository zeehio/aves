# -*- coding: utf-8 -*-
import errno
import json
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


def _reject_yaml_extension(source_name):
    if source_name.endswith((".yaml", ".yml")):
        raise ValueError(
            f"{source_name} looks like a YAML file. Aves configs are TOML "
            "(config.toml) or JSON (config.json), not YAML. Please convert "
            "it -- see the README for the schema.")


def _loads_toml_or_json(text, source_name):
    "Parses text as JSON if source_name ends in '.json', TOML otherwise."
    if source_name.endswith(".json"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not parse {source_name} as JSON: {exc}") from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Could not parse {source_name} as TOML: {exc}") from exc


def parse_config_text(text, source_name="config.toml"):
    """
    Parses already-read TOML or JSON config text (picked by source_name's
    extension), validating its 'version' key. Shared by parse_config
    (reading from disk) and the web settings editor (validating text a
    browser is about to save, before it touches disk).
    """
    _reject_yaml_extension(source_name)
    data = _loads_toml_or_json(text, source_name)
    if "version" not in data:
        raise ValueError(
            f"{source_name} is missing the required 'version' key "
            "(expected version = 3)")
    if data["version"] != 3:
        raise ValueError(
            f"{source_name} has version {data['version']!r}, but this "
            "version of aves only supports config files with version = 3")
    return data


def parse_config(config_file="config.toml"):
    _reject_yaml_extension(config_file)
    with open(config_file, "r", encoding="utf-8") as stream:
        text = stream.read()
    return parse_config_text(text, source_name=config_file)
