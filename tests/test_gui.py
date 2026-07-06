import subprocess
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from aves.gui import SensorViewerGUI

GUI_CONFIG = {
    "x_column": "t",
    "zoom_all_together": True,
    "window_title": "Test",
    "refresh_time_ms": 100,
    "axes": [
        {"name": "A", "row": 0, "col": 0, "columns": ["a"], "ylabel": "A"},
        {"name": "B", "row": 1, "col": 0, "columns": ["b"], "ylabel": "B"},
    ],
}


def test_gui_has_no_tk_dependency():
    """aves.gui must stay importable without Tk: SensorViewerGUI only needs
    matplotlib. The Tk-only file dialogs live in aves.dialogs instead. Run
    in a subprocess for a clean interpreter, independent of what other
    tests may have already imported."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys\n"
         "import aves.gui\n"
         "assert 'tkinter' not in sys.modules\n"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def gui_window():
    window = SensorViewerGUI(config=GUI_CONFIG)
    yield window
    plt.close(window.fig)


def test_gui_creates_one_axis_per_configured_subplot(gui_window):
    assert len(gui_window.axes) == 2
    assert set(gui_window.points.keys()) == {"a", "b"}


def test_gui_render_updates_line_data_without_raising(gui_window):
    data = {"t": [0, 1, 2], "a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}
    gui_window.render(data)
    assert list(gui_window.points["a"].get_ydata()) == [1.0, 2.0, 3.0]
    assert list(gui_window.points["b"].get_ydata()) == [3.0, 2.0, 1.0]


def test_gui_closed_reflects_figure_lifecycle(gui_window):
    assert not gui_window.closed
    plt.close(gui_window.fig)
    assert gui_window.closed


def test_gui_requires_top_level_keys():
    with pytest.raises(ValueError, match="'gui' section.*axes, x_column"):
        SensorViewerGUI(config={"zoom_all_together": True})


def test_gui_requires_axes_to_be_a_list():
    config = {
        "x_column": "t",
        "zoom_all_together": False,
        "axes": {"A": {"columns": ["a"]}},  # old dict-based shape
    }
    with pytest.raises(ValueError, match=r"array of tables.*\[\[gui\.axes\]\]"):
        SensorViewerGUI(config=config)


def test_gui_axis_without_style_fields_still_works():
    config = {
        "x_column": "t",
        "zoom_all_together": False,
        "axes": [
            {"name": "A", "columns": ["a"]},  # no style fields at all
        ],
    }
    window = SensorViewerGUI(config=config)
    try:
        assert set(window.points.keys()) == {"a"}
    finally:
        plt.close(window.fig)


def test_gui_applies_curated_style_fields(gui_window):
    ax = gui_window.axes[0]
    assert ax.get_ylabel() == "A"


def test_gui_rejects_unknown_axis_keys():
    config = {
        "x_column": "t",
        "zoom_all_together": False,
        "axes": [
            {"name": "A", "columns": ["a"], "facecolor": "red"},
        ],
    }
    with pytest.raises(ValueError, match="unknown key.*facecolor"):
        SensorViewerGUI(config=config)
