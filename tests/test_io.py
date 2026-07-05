import pytest

from aves.io import DataBuffers, ReadSensorFile, ReadSensorSerial, WriteSensorFile


class FakeSerialPort:
    """Stands in for a pyserial Serial object: readline() pops canned lines."""

    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0)


def test_databuffers_append_and_appendleft():
    buffers = DataBuffers()
    buffers.append({"x": 1})
    buffers.append({"x": 2})
    buffers.appendleft({"x": 0})
    assert list(buffers.data["x"]) == [0, 1, 2]


def test_databuffers_extend_and_extendleft():
    buffers = DataBuffers()
    buffers.extend([{"x": 1}, {"x": 2}])
    buffers.extendleft([{"x": -1}, {"x": 0}])
    # extendleft appends each sample to the left in order, like deque.appendleft
    assert list(buffers.data["x"]) == [0, -1, 1, 2]


def test_databuffers_maxlen_drops_oldest_samples():
    buffers = DataBuffers(maxlen=2)
    buffers.extend([{"x": 1}, {"x": 2}, {"x": 3}])
    assert list(buffers.data["x"]) == [2, 3]


def test_databuffers_set_maxlen_keeps_most_recent_samples():
    buffers = DataBuffers(maxlen=None)
    buffers.extend([{"x": 1}, {"x": 2}, {"x": 3}])
    buffers.set_maxlen(maxlen=2)
    assert list(buffers.data["x"]) == [2, 3]
    assert buffers.maxlen == 2
    # buffer should now actually be capped
    buffers.append({"x": 4})
    assert list(buffers.data["x"]) == [3, 4]


def test_databuffers_set_maxlen_none_keeps_all_samples():
    buffers = DataBuffers(maxlen=2)
    buffers.extend([{"x": 1}, {"x": 2}])
    buffers.set_maxlen(maxlen=None)
    buffers.append({"x": 3})
    assert list(buffers.data["x"]) == [1, 2, 3]


def test_write_then_read_round_trip(tmp_path):
    outfile = tmp_path / "out.txt"
    columns = ["time_computer", "value"]
    config = {"columns": columns}
    with WriteSensorFile(filename=str(outfile), config=config) as writer:
        writer.write([
            {"time_computer": "2020-01-01T00:00:00", "value": 1.5},
            {"time_computer": "2020-01-01T00:00:01", "value": 2.5},
        ])

    with ReadSensorFile(filename=str(outfile), config=config) as reader:
        samples = reader.readsamples()

    assert len(samples) == 2
    # The first column is read back as a raw string, the rest as floats.
    assert samples[0] == {"time_computer": "2020-01-01T00:00:00", "value": 1.5}
    assert samples[1] == {"time_computer": "2020-01-01T00:00:01", "value": 2.5}


def test_read_skips_comments_and_blank_lines(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text(
        "# a comment line\n"
        "\n"
        "1\t2.0\n"
        "   \n"
        "# another comment\n"
        "3\t4.0\n"
    )
    config = {"columns": ["a", "b"]}
    with ReadSensorFile(filename=str(infile), config=config) as reader:
        samples = reader.readsamples()

    assert samples == [
        {"a": "1", "b": 2.0},
        {"a": "3", "b": 4.0},
    ]


def test_readsamples_respects_num_samples_limit(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n3\t4.0\n5\t6.0\n")
    config = {"columns": ["a", "b"]}
    with ReadSensorFile(filename=str(infile), config=config) as reader:
        samples = reader.readsamples(num_samples=2)

    assert len(samples) == 2


def test_readsample_returns_none_at_eof(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    config = {"columns": ["a", "b"]}
    with ReadSensorFile(filename=str(infile), config=config) as reader:
        first = reader.readsample()
        second = reader.readsample()

    assert first == {"a": "1", "b": 2.0}
    assert second is None


def test_read_sensor_file_requires_columns(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    with pytest.raises(ValueError, match="'output' section.*columns"):
        ReadSensorFile(filename=str(infile), config={})


def test_write_sensor_file_requires_columns(tmp_path):
    outfile = tmp_path / "out.txt"
    with pytest.raises(ValueError, match="'output' section.*columns"):
        WriteSensorFile(filename=str(outfile), config={})


def _make_serial_reader(columns, **kwargs):
    config = {
        "arduino": {
            "baudrate": 9600,
            "timeout": 1,
            "columns": columns,
        }
    }
    return ReadSensorSerial(port="/dev/fake", config=config, **kwargs)


def test_readsensorserial_requires_arduino_section():
    with pytest.raises(ValueError, match="'input' section.*arduino"):
        ReadSensorSerial(port="/dev/fake", config={})


def test_readsensorserial_requires_arduino_keys():
    config = {"arduino": {"columns": []}}
    with pytest.raises(ValueError, match="'input.arduino' section.*baudrate, timeout"):
        ReadSensorSerial(port="/dev/fake", config=config)


def test_readsensorserial_requires_column_keys():
    config = {
        "arduino": {
            "baudrate": 9600,
            "timeout": 1,
            "columns": [{"name": "a"}],  # missing conversion_factor
        }
    }
    with pytest.raises(ValueError, match=r"columns\[0\].*conversion_factor"):
        ReadSensorSerial(port="/dev/fake", config=config)


def test_readsensorserial_skips_garbage_and_logs_warning(caplog):
    reader = _make_serial_reader([{"name": "a", "conversion_factor": 1.0}])
    reader._inputdata = FakeSerialPort([b"not-a-number\n", b"3.0\n"])

    with caplog.at_level("WARNING"):
        sample = reader.readsample()

    assert sample["a"] == 3.0
    assert "Discarding garbage" in caplog.text


def test_readsensorserial_warns_on_field_count_mismatch(caplog):
    reader = _make_serial_reader([
        {"name": "a", "conversion_factor": 1.0},
        {"name": "b", "conversion_factor": 2.0},
    ])
    reader._inputdata = FakeSerialPort([b"1.0\n", b"1.0\t2.0\n"])

    with caplog.at_level("WARNING"):
        sample = reader.readsample()

    assert sample["a"] == 1.0
    assert sample["b"] == 4.0
    assert "expecting 2" in caplog.text


def test_readsensorserial_gives_up_after_max_consecutive_garbage_lines(caplog):
    reader = _make_serial_reader(
        [{"name": "a", "conversion_factor": 1.0}],
        max_consecutive_garbage_lines=3)
    reader._inputdata = FakeSerialPort([b"garbage\n", b"garbage\n", b"garbage\n"])

    with caplog.at_level("WARNING"):
        sample = reader.readsample()

    assert sample is None
    assert reader.stop_sampling
    assert "Giving up after 3 consecutive unusable lines" in caplog.text


def test_readsensorserial_resets_garbage_count_after_a_good_sample(caplog):
    """A run of garbage shorter than the limit, followed by a good sample,
    must not count towards the give-up threshold on the next call."""
    reader = _make_serial_reader(
        [{"name": "a", "conversion_factor": 1.0}],
        max_consecutive_garbage_lines=2)
    reader._inputdata = FakeSerialPort([
        b"garbage\n", b"1.0\n",  # first call: 1 garbage line, then recovers
        b"garbage\n", b"2.0\n",  # second call: same again
    ])

    first = reader.readsample()
    second = reader.readsample()

    assert first["a"] == 1.0
    assert second["a"] == 2.0
    assert not reader.stop_sampling
