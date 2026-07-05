import subprocess
import sys

from aves.acquisition import Acquisition
from aves.io import DataBuffers, ReadSensorFile, WriteSensorFile

COLUMNS_CONFIG = {"columns": ["a", "b"]}


def test_acquisition_has_no_gui_dependency():
    """aves.acquisition must stay importable without matplotlib/tkinter,
    so the acquisition logic is testable without a display. Run in a
    subprocess for a clean interpreter, independent of what other tests
    may have already imported."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys\n"
         "import aves.acquisition\n"
         "assert 'tkinter' not in sys.modules\n"
         "assert 'matplotlib' not in sys.modules\n"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_acquisition_step_reads_writes_and_buffers(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n3\t4.0\n5\t6.0\n")
    outfile_path = tmp_path / "out.txt"

    buffers = DataBuffers()
    with ReadSensorFile(filename=str(infile), config=COLUMNS_CONFIG) as idev, \
            WriteSensorFile(filename=str(outfile_path), config=COLUMNS_CONFIG) as outfile:
        acquisition = Acquisition(idev=idev, buffers=buffers, outfile=outfile,
                                   samples_per_step=2)
        samples = acquisition.step()

    assert len(samples) == 2
    # extendleft prepends each sample in turn, so the batch ends up reversed
    assert list(buffers.data["a"]) == ["3", "1"]
    assert list(buffers.data["b"]) == [4.0, 2.0]

    written_lines = outfile_path.read_text().splitlines()
    assert written_lines[2:] == ["1\t2.0", "3\t4.0"]


def test_acquisition_without_outfile_only_buffers(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")

    buffers = DataBuffers()
    with ReadSensorFile(filename=str(infile), config=COLUMNS_CONFIG) as idev:
        acquisition = Acquisition(idev=idev, buffers=buffers, samples_per_step=1)
        acquisition.step()

    assert list(buffers.data["a"]) == ["1"]


def test_acquisition_should_stop_when_input_exhausted(tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("1\t2.0\n")

    buffers = DataBuffers()
    with ReadSensorFile(filename=str(infile), config=COLUMNS_CONFIG) as idev:
        acquisition = Acquisition(idev=idev, buffers=buffers, samples_per_step=5)
        assert not acquisition.should_stop()
        acquisition.step()
        assert acquisition.should_stop()


def test_acquisition_should_stop_when_time_limit_exceeded():
    class NeverEndingSource:
        stop_sampling = False

        def readsamples(self, num_samples):
            return []

    buffers = DataBuffers()
    acquisition = Acquisition(idev=NeverEndingSource(), buffers=buffers, tmeas=-1)
    assert acquisition.should_stop()
