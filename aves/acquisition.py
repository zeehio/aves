# -*- coding: utf-8 -*-
"""
Owns the "read a batch of samples, write them, buffer them, decide whether to
keep going" loop. This module has no knowledge of how (or whether) the
results get displayed: it only ever imports :py:mod:`aves.io` and the
standard library, so it can be imported and tested without matplotlib or
Tk installed.
"""

import datetime


class Acquisition(object):
    """
    Reads samples from ``idev``, optionally writes them to ``outfile``, and
    buffers them in ``buffers``. A presentation layer (a GUI, a script, a
    test) reads ``buffers.data`` after each :py:meth:`step` -- it is never
    called into from here.

    Args:
        idev: An open :py:class:`aves.io.ReadSensorAbstract` instance.
        buffers (aves.io.DataBuffers): Where read samples are accumulated.
        outfile: An open :py:class:`aves.io.WriteSensorFile` instance, or
            ``None`` to skip writing samples to disk.
        tmeas (float): Stop once this many seconds have elapsed since
            construction (default: unlimited).
        samples_per_step (int): How many samples :py:meth:`step` reads at
            a time.
    """

    def __init__(self, idev, buffers, outfile=None, tmeas=float('inf'),
                 samples_per_step=10):
        self.idev = idev
        self.buffers = buffers
        self.outfile = outfile
        self.tmeas = tmeas
        self.samples_per_step = samples_per_step
        self._start = datetime.datetime.now()

    def step(self):
        """
        Reads a batch of samples, writes them (if there is an outfile), and
        buffers them.

        Returns:
            list: The samples read (possibly empty).
        """
        samples = self.idev.readsamples(num_samples=self.samples_per_step)
        if self.outfile is not None:
            self.outfile.write(samples)
        self.buffers.extendleft(samples)
        return samples

    def should_stop(self):
        """
        True once the time limit has been reached or the input device has
        run out of samples. Does not know about (or care whether) a GUI
        window is open -- that is a separate, presentation-layer concern.
        """
        elapsed = (datetime.datetime.now() - self._start).total_seconds()
        return elapsed > self.tmeas or self.idev.stop_sampling
