import pytest

from aves.io import ReadSensorFile, ReadSensorSerial, WriteSensorFile
from aves.wiring import build_input_device, build_output_device


def test_build_input_device_replays_an_existing_file(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    config = {"output": {"columns": ["a", "b"]}}
    idev = build_input_device(str(infile), config)
    assert isinstance(idev, ReadSensorFile)


def test_build_input_device_uses_serial_for_a_nonexistent_path():
    config = {
        "input": {
            "arduino": {
                "baudrate": 9600, "timeout": 1,
                "columns": [{"name": "a"}],
            }
        }
    }
    idev = build_input_device("/dev/definitely-not-a-real-path", config)
    assert isinstance(idev, ReadSensorSerial)


def test_build_input_device_requires_output_section_for_file_replay(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    with pytest.raises(ValueError, match="output"):
        build_input_device(str(infile), config={})


def test_build_input_device_requires_input_section_for_serial():
    with pytest.raises(ValueError, match="input"):
        build_input_device("/dev/definitely-not-a-real-path", config={})


def test_build_output_device_returns_none_without_output_section():
    assert build_output_device("out.txt", config={}) is None


def test_build_output_device_returns_a_writer_with_output_section(tmp_path):
    outfile = tmp_path / "out.txt"
    config = {"output": {"columns": ["a", "b"]}}
    dev = build_output_device(str(outfile), config)
    assert isinstance(dev, WriteSensorFile)
