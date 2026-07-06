import threading
import types

import pytest

from aves.io import DataBuffers, ReadSensorFile
from aves.acquisition import Acquisition
from aves.web.__main__ import AcquisitionManager, _acquisition_loop


class FakeBroadcaster:
    def __init__(self):
        self.ready = threading.Event()
        self.ready.set()
        self.published = []

    def publish(self, message):
        self.published.append(message)


def test_acquisition_loop_publishes_each_batch_until_input_exhausted(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n3\t4.0\n")
    config = {"columns": ["a", "b"]}
    broadcaster = FakeBroadcaster()

    with ReadSensorFile(filename=str(infile), config=config) as idev:
        acquisition = Acquisition(idev=idev, buffers=DataBuffers(), samples_per_step=1)
        stop_event = threading.Event()
        _acquisition_loop(acquisition, broadcaster, stop_event)

    # 3 publishes for 2 lines: buffers.data guard checks "has ever had
    # data", not "changed this step", so the step that discovers EOF
    # (empty batch, but buffers still non-empty from before) publishes
    # once more before should_stop() finally trips -- same accepted
    # pattern already in realtime.py's _tick(), not new here.
    assert len(broadcaster.published) == 3
    assert broadcaster.published[1] == broadcaster.published[2] == {
        "a": ["3", "1"], "b": [4.0, 2.0]}
    # values are plain lists (JSON-serializable), not deques
    assert isinstance(broadcaster.published[-1]["a"], list)


def test_acquisition_loop_waits_for_broadcaster_ready(tmp_path):
    """Must actually block on ready, not just happen to publish after it
    gets set. A broadcaster that records whether it was ready at the
    moment of each publish() call would catch a regression where the
    wait() gets dropped -- a plain delay-then-set fake wouldn't."""
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    config = {"columns": ["a", "b"]}

    class ReadinessTrackingBroadcaster(FakeBroadcaster):
        def __init__(self):
            super().__init__()
            self.was_ready_at_publish = []

        def publish(self, message):
            self.was_ready_at_publish.append(self.ready.is_set())
            super().publish(message)

    broadcaster = ReadinessTrackingBroadcaster()
    broadcaster.ready.clear()

    def set_ready_after_delay():
        import time
        time.sleep(0.1)
        broadcaster.ready.set()

    with ReadSensorFile(filename=str(infile), config=config) as idev:
        acquisition = Acquisition(idev=idev, buffers=DataBuffers(), samples_per_step=1)
        stop_event = threading.Event()
        releaser = threading.Thread(target=set_ready_after_delay)
        releaser.start()
        _acquisition_loop(acquisition, broadcaster, stop_event)
        releaser.join()

    # 2, not 1: see the comment in the previous test -- the
    # EOF-detecting step re-publishes the same (by-then-unchanged)
    # data once more.
    assert len(broadcaster.published) == 2
    assert broadcaster.was_ready_at_publish == [True, True]


def test_acquisition_loop_stops_when_stop_event_is_set_between_batches(tmp_path):
    infile = tmp_path / "in.txt"
    # more lines than will actually be consumed, thanks to stop_event
    infile.write_text("\n".join(f"{i}\t{i}.0" for i in range(1000)) + "\n")
    config = {"columns": ["a", "b"]}

    class StoppingBroadcaster(FakeBroadcaster):
        def publish(self, message):
            super().publish(message)
            if len(self.published) >= 3:
                stop_event.set()

    broadcaster = StoppingBroadcaster()
    stop_event = threading.Event()

    with ReadSensorFile(filename=str(infile), config=config) as idev:
        acquisition = Acquisition(idev=idev, buffers=DataBuffers(), samples_per_step=1)
        _acquisition_loop(acquisition, broadcaster, stop_event)

    assert len(broadcaster.published) == 3


def _write_config(path, x_column="a", columns=("a", "b")):
    columns_toml = ", ".join(f'"{c}"' for c in columns)
    path.write_text(
        "version = 3\n\n"
        "[gui]\n"
        f'x_column = "{x_column}"\n'
        "zoom_all_together = true\n"
        "axes = []\n\n"
        "[output]\n"
        f"columns = [{columns_toml}]\n")


def _make_args(port, config_file, outfile=None, plot_win_size=None,
               tmeas=float('inf'), plot_every_n_samples=1):
    return types.SimpleNamespace(
        port=port, config_file=config_file, outfile=outfile,
        plot_win_size=plot_win_size, tmeas=tmeas,
        plot_every_n_samples=plot_every_n_samples)


def _make_app():
    return types.SimpleNamespace(
        state=types.SimpleNamespace(broadcaster=FakeBroadcaster(), gui_config=None))


def test_acquisition_manager_start_and_stop(tmp_path):
    from aves.utils import parse_config

    config_file = tmp_path / "config.toml"
    _write_config(config_file)
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n3\t4.0\n")

    args = _make_args(port=str(infile), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file))

    manager.start(config)
    assert manager.is_running
    assert app.state.gui_config == config["gui"]

    manager.stop()
    assert not manager.is_running
    assert app.state.broadcaster.published


def test_acquisition_manager_start_twice_raises(tmp_path):
    from aves.utils import parse_config

    config_file = tmp_path / "config.toml"
    _write_config(config_file)
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    args = _make_args(port=str(infile), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file))

    manager.start(config)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            manager.start(config)
    finally:
        manager.stop()


def test_acquisition_manager_stop_without_start_is_a_noop(tmp_path):
    config_file = tmp_path / "config.toml"
    _write_config(config_file)
    args = _make_args(port=str(tmp_path / "in.txt"), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)

    manager.stop()
    assert not manager.is_running


def test_acquisition_manager_start_cleans_up_on_failure(tmp_path):
    from aves.utils import parse_config

    config_file = tmp_path / "config.toml"
    # No "output" section: build_input_device requires one for file replay.
    config_file.write_text(
        'version = 3\n\n[gui]\nx_column = "a"\nzoom_all_together = true\naxes = []\n')
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    args = _make_args(port=str(infile), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file))

    with pytest.raises(ValueError):
        manager.start(config)
    assert not manager.is_running


def test_acquisition_manager_restart_reloads_config_from_disk(tmp_path):
    from aves.utils import parse_config

    config_file = tmp_path / "config.toml"
    _write_config(config_file, x_column="a")
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    args = _make_args(port=str(infile), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file))
    manager.start(config)

    # Simulate the settings editor having saved a change to disk.
    _write_config(config_file, x_column="b")

    new_gui_config = manager.restart()

    assert new_gui_config["x_column"] == "b"
    assert app.state.gui_config["x_column"] == "b"
    assert manager.is_running
    manager.stop()


def test_acquisition_manager_restart_can_switch_config_path(tmp_path):
    from aves.utils import parse_config

    config_file_a = tmp_path / "a.toml"
    config_file_b = tmp_path / "b.toml"
    _write_config(config_file_a, x_column="a")
    _write_config(config_file_b, x_column="b")
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    args = _make_args(port=str(infile), config_file=str(config_file_a))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file_a))
    manager.start(config)

    new_gui_config = manager.restart(config_path=str(config_file_b))

    assert new_gui_config["x_column"] == "b"
    assert args.config_file == str(config_file_b)
    manager.stop()


def test_acquisition_manager_restart_failure_leaves_nothing_running(tmp_path):
    """restart() doesn't roll back: if the new config fails to build, the
    old acquisition has already been stopped, so nothing is running
    afterwards -- the caller (the web /api/settings/restart endpoint) is
    expected to surface the raised error rather than pretend it worked."""
    from aves.utils import parse_config

    config_file = tmp_path / "config.toml"
    _write_config(config_file, x_column="a")
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")
    args = _make_args(port=str(infile), config_file=str(config_file))
    app = _make_app()
    manager = AcquisitionManager(app, args)
    config = parse_config(config_file=str(config_file))
    manager.start(config)

    broken_config_file = tmp_path / "broken.toml"
    broken_config_file.write_text('version = 3\n\n[gui]\nx_column = "a"\n')

    with pytest.raises(ValueError):
        manager.restart(config_path=str(broken_config_file))
    assert not manager.is_running
