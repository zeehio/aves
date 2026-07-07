import os

import pytest

from aves.utils import mkdir_p, parse_config, require_keys


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
    config_file = tmp_path / "config.toml"
    config_file.write_text('version = 3\nfoo = "bar"\n')
    data = parse_config(config_file=str(config_file))
    assert data == {"version": 3, "foo": "bar"}


def test_parse_config_rejects_wrong_version(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("version = 2\n")
    with pytest.raises(ValueError, match="version"):
        parse_config(config_file=str(config_file))


def test_parse_config_rejects_missing_version(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('foo = "bar"\n')
    with pytest.raises(ValueError, match="version"):
        parse_config(config_file=str(config_file))


def test_parse_config_rejects_invalid_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("version = 3\n  bad [[[ \n")
    with pytest.raises(ValueError, match="TOML"):
        parse_config(config_file=str(config_file))


def test_parse_config_reads_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"version": 3, "foo": "bar"}')
    data = parse_config(config_file=str(config_file))
    assert data == {"version": 3, "foo": "bar"}


def test_parse_config_rejects_invalid_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{not valid json")
    with pytest.raises(ValueError, match="JSON"):
        parse_config(config_file=str(config_file))


def test_parse_config_rejects_wrong_version_in_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"version": 2}')
    with pytest.raises(ValueError, match="version"):
        parse_config(config_file=str(config_file))


def test_parse_config_rejects_yaml_extension(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("version: 3\n")
    with pytest.raises(ValueError, match="YAML"):
        parse_config(config_file=str(config_file))


def test_require_keys_passes_through_when_all_present():
    mapping = {"a": 1, "b": 2}
    assert require_keys(mapping, ["a", "b"], "some section") is mapping


def test_require_keys_reports_missing_keys_by_name():
    with pytest.raises(ValueError, match=r"missing required key\(s\): b, c"):
        require_keys({"a": 1}, ["a", "b", "c"], "some section")


def test_require_keys_names_the_section_in_the_error():
    with pytest.raises(ValueError, match="the 'arduino' section"):
        require_keys({}, ["baudrate"], "the 'arduino' section")


def test_require_keys_rejects_non_mapping():
    with pytest.raises(ValueError, match="must be a mapping"):
        require_keys(["not", "a", "dict"], ["a"], "some section")
