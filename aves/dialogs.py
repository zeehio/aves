# -*- coding: utf-8 -*-
"""
Tk "open file"/"choose directory" dialogs used by the CLI entry points
when no --filename/--destdir is given. Kept separate from
:py:mod:`aves.gui` so that module (matplotlib-only) can be imported and
tested without Tk installed.
"""

import tkinter
from tkinter.filedialog import askopenfilename, askdirectory


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
