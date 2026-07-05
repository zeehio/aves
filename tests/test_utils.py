import os

import pytest

from aves.utils import mkdir_p, parse_config


def test_mkdir_p_creates_nested_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    mkdir_p(str(target))
    assert target.is_dir()


def test_mkdir_p_is_idempotent(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    mkdir_p(str(target))  # must not raise
    assert target.is_dir()


def test_mkdir_p_empty_path_is_noop():
    mkdir_p("")  # must not raise


def test_parse_config_valid(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("version: 2\nfoo: bar\n")
    data = parse_config(config_file=str(config_file))
    assert data == {"version": 2, "foo": "bar"}


def test_parse_config_rejects_wrong_version(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("version: 1\n")
    with pytest.raises(ValueError):
        parse_config(config_file=str(config_file))


def test_parse_config_rejects_json_extension():
    with pytest.raises(ValueError):
        parse_config(config_file="config.json")
