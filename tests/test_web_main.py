import threading

from aves.io import DataBuffers, ReadSensorFile
from aves.acquisition import Acquisition
from aves.web.__main__ import _acquisition_loop


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
