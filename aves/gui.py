# -*- coding: utf-8 -*-
"""
The graphical user interface is defined in :py:class:`SensorViewerGUI`. This
class creates the figure with the axes and the plots of the GUI.

This class:

 - Creates a figure that contains all the plots in
   :py:class:`SensorViewerGUI._create_figure`.
 - Creates an axes for each plot we want in
   :py:class:`SensorViewerGUI._create_axes`. Note that the labels are created
   at :py:class:`SensorViewerGUI._set_axes_properties`.
 - Prepares the plots (initially without any data) that will appear on each
   axes :py:class:`SensorViewerGUI._create_points`.

Additionally, this class provides an interface so the main program can:

 - Draw the latest data :py:class:`SensorViewerGUI.render`. A small delay is
   introduced so the user can move and resize the window interactively.
 - Drive a loop with :py:class:`SensorViewerGUI.run`, calling back into a
   caller-supplied function on every refresh until it says to stop or the
   window is closed.

It gives further options to:

 - Optionally use the same ``time`` axis on all the plots.
 - Report whether the window has been closed by the user
   (:py:class:`SensorViewerGUI.closed`).
 - Keep the window of the program open until it is closed by the user

This module intentionally knows nothing about how data is acquired --
see :py:mod:`aves.acquisition` for that.

"""


import tkinter
from tkinter.filedialog import askopenfilename, askdirectory

import matplotlib.pyplot as plt
from matplotlib import animation


def _get_plot_shape(config_axes):
    plot_rows = 0
    plot_cols = 0
    for k, v in config_axes.items():
        r = v.get("row", 0) + v.get("rowspan", 1)
        c = v.get("col", 0) + v.get("colspan", 1)
        if r > plot_rows:
            plot_rows = r
        if c > plot_cols:
            plot_cols = c
    return (plot_rows, plot_cols)


class SensorViewerGUI(object):
    """
    Creates and shows a figure with plots of the sensors
    """

    def __init__(self, config):
        # Make sure sharex is boolean
        self._config = config
        self.fig = None
        self.axes = None
        self.points = None
        self._plotshape = None
        self._sharex = bool(self._config["zoom_all_together"])
        self._sharexaxis = None
        self._xlimits = None
        self._create_figure()
        self._create_axes()
        self._create_points()
        self.fig.show()

    def run(self, tick):
        """
        Drives the GUI's refresh timer, calling ``tick()`` on every frame
        until it returns a falsy value or the window is closed by the user.

        ``tick`` is entirely opaque to this method: it may read data, write
        files, check stop conditions -- this class does not need to know.
        """
        def _animate(framenum):
            if self.closed or not tick():
                self.ani.event_source.stop()
                return []
            return list(self.axes.values())
        interval = self._config.get("refresh_time_ms", 100)
        self.ani = animation.FuncAnimation(self.fig, _animate,
                                           frames=None, interval=interval, repeat=False)
        plt.show()

    def _create_figure(self):
        """ Creates a figure: The main window of the application. It sets
        the style of the plots that will be used in the figure.

        """
        fig = plt.figure()
        plt.style.use('ggplot')  # pylint: disable=E1101
        if fig.canvas.manager is not None:
            fig.canvas.manager.set_window_title(
                self._config.get("window_title", "Figure 1"))
        self.fig = fig
        return

    def toogle_sharex(self):
        """ Toogle whether or not the x axis is shared when zooming"""
        self.set_sharex(sharex=not self._sharex)

    def set_sharex(self, sharex=False):
        """ Set whether or not the x axis is shared when zooming"""
        if sharex != self._sharex:
            self._sharex = sharex
            self._create_axes()
            self._create_points()
        return

    def get_sharex(self):
        """ Get if the x axis is shared when zooming"""
        return self._sharex

    def _create_axes(self):
        """ Creates the axis object """
        config_axes = self._config["axes"]
        axes = dict()

        # The first row is for the temperature and humidity plots
        self._plotshape = _get_plot_shape(config_axes)
        self._sharexaxis = None
        for axis_name, axis_vals in config_axes.items():
            row_col = (axis_vals.get("row", 0), axis_vals.get("col", 0))
            rowspan = axis_vals.get("rowspan", 1)
            colspan = axis_vals.get("colspan", 1)
            axes[axis_name] = plt.subplot2grid(self._plotshape,
                                               row_col, rowspan=rowspan, colspan=colspan, sharex=self._sharexaxis)
            if self._sharex and self._sharexaxis is None:
                self._sharexaxis = axes[axis_name]
        self.axes = axes
        self.set_axes_properties()
        return

    def _create_points(self):
        """ Create matplotlib lines objects, where the data is stored """
        points = dict()
        config_axes = self._config["axes"]
        for axis_name, axis_vals in config_axes.items():
            point_ids = axis_vals.get("columns", [])
            point_legend = axis_vals.get("columns_legend", point_ids)
            for points_id in point_ids:
                points[points_id] = self.axes[axis_name].plot([], [])[0]
            if len(point_ids) > 1:
                self.axes[axis_name].legend([points[x] for x in point_ids],
                                            point_legend)
        # Update points data with data from self.points:
        if self.points is None:
            self.points = points
            return
        for (sensor, mpl_line) in points.items():
            times = self.points[sensor].get_xdata()
            values = self.points[sensor].get_ydata()
            mpl_line.set_data(times, values)
        self.points = points
        return

    def set_axes_properties(self):
        """
        Sets defaults limits and labels for the plot axes
        """
        config_axes = self._config["axes"]
        for (axis_name, ax_opt) in config_axes.items():
            self.axes[axis_name].set(**ax_opt["options"])
        return

    def set_xlim(self, xlimits=None):
        "Sets the xlim on all axes"
        if xlimits is None:
            if self._xlimits is None:
                return
            xlimits = self._xlimits
        for axname, axis in self.axes.items():
            axis.set_xlim(xlimits)
        return

    def render(self, data):
        """
        Draws the given data and refreshes the window.

        Args:
            data (dict): Iterables to copy the data from, keyed by column
                name (as configured in ``x_column`` and each axis'
                ``columns``).

        """
        x_key = self._config["x_column"]
        for sensor in self.points.keys():
            self.points[sensor].set_data(data[x_key], data[sensor])
        self._xlimits = (data[x_key][0], data[x_key][-1])
        self.set_xlim()
        self.fig.canvas.draw()
        plt.pause(0.025)

    @property
    def closed(self):
        "Whether the window has been closed by the user"
        return not plt.fignum_exists(self.fig.number)

    def wait_until_close(self):  # pylint: disable=R0201
        "Wait until the window is closed"
        plt.show(block=True)


def filename_from_dialog(path):
    """ Creates a open file dialog and returns the filename"""
    root = None
    try:
        # we don't want a full GUI, so keep the root window from appearing
        root = tkinter.Tk()
        # show an "Open" dialog box and return the path to the selected file
        filename = askopenfilename(initialdir=path)
        if len(filename) == 0:
            raise ValueError("No filename selected")
    finally:
        if root is not None:
            root.destroy()
    return filename


def dirname_from_dialog(path):
    """ Creates a open directory dialog and returns the directory path"""
    root = None
    try:
        # we don't want a full GUI, so keep the root window from appearing
        root = tkinter.Tk()
        # show an "Open" dialog box and return the path to the selected file
        directory = askdirectory(initialdir=path)
        if len(directory) == 0:
            raise ValueError("No directory selected")
    finally:
        if root is not None:
            root.destroy()
    return directory
