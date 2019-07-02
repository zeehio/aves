# -*- coding: utf-8 -*-
"""
Overview
----------

This module deals with reading and writing sensor data from an Arduino.
It takes care of:

 - **Reading data from the serial port** (useful for online data acquisition)
 - **Writing data to a file** (useful for storing the data we read from the
   serial port)
 - **Reading data from a file** (useful for offline analysis of data)

Reading samples
------------------

Acquiring samples from any device or file requires to:

 1. Open device or file
 2. Read sample (or batch of samples)
 3. Close the device or file (when finished)

This idea is expressed in :py:class:`ReadSensorAbstract`. We define the
*acquisition system* that must define:

 - An ``open`` and a ``close`` method.
 - A ``readsample`` method and a ``readsamples`` method.
 - A ``stop_sampling`` property (is ``True`` if we have read all samples)

The advantage of having this abstract class stating "what actions have to be
implemented" is that if in the future we want a ``ReadSensorWifi`` we only
need to implement the open/read/close methods and it will work directly.


Reading from serial port
+++++++++++++++++++++++++

We define :py:class:`ReadSensorSerial`, that implements the methods to read
from a serial port.

Reading from a file
++++++++++++++++++++

We define :py:class:`ReadSensorFile`, that implements the methods to read
from a conventional file.

Long experiments and memory usage
------------------------------------

To prevent the system from crashing on very long experiments, we will
store the samples on disk on the fly and we will only keep the last N points
in memory for plotting. To do that, we will use the :py:class:`DataBuffers`.

This class is also used to control the number of points we want to plot in
the online analysis (plots with too many points also consume more memory).

"""

# Based on code from Mahesh Venkitachalam available at electronut.in

from __future__ import print_function
import os
import errno
from collections import deque
import datetime
from collections import defaultdict
from functools import partial
import serial

TIME_COMPUTER = "time_computer"

def mkdir_p(path):
    "Creates a directory, recursively if necessary"
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

class ReadSensorAbstract(object):
    """ Abstract class to read a sensor sample.

    It has to implement an open method, a close method, a readsample method,
    a readsamples method and a stop_sampling property.
    """
    def __init__(self):
        self._stop_sampling = False

    def __enter__(self, *args, **kwargs):
        self.open(*args, **kwargs)
        return self

    def __exit__(self, typ, value, traceback):
        self.close()
        if typ is None:
            return True
        else:
            return False

    def open(self, *args, **kwargs):
        """ Opens the file or serial port where the input is coming from."""
        raise NotImplementedError("open not implemented")

    def close(self):
        """ Closes the file or serial port where the input is coming from."""
        raise NotImplementedError("close not implemented")

    def readsample(self, *args, **kwargs):
        """
        Reads a single sample from the input.
        Returns a dictionary with the values of each sensor and the time.
        """
        raise NotImplementedError("readsample not implemented")

    def readsamples(self, num_samples):
        """
        Reads a num_samples samples from the input.
        Returns a list with samples as given by readsample.
        """
        raise NotImplementedError("readsamples not implemented")

    @property
    def stop_sampling(self):
        """
        Returns True when we should not get more samples (for instance if
        we have reached an end of file)
        """
        return self._stop_sampling


class ReadSensorFile(ReadSensorAbstract):
    """
    Reads a file written by ReadSensorSerial allowing to load experiments
    already measured and stored

    Args:
        filename (str): File where the experiment has been saved
    """
    def __init__(self, filename, config):
        super(ReadSensorFile, self).__init__()
        self._filename = filename
        self._file = None
        self._file_columns = config.get("columns", [])
        return

    def open(self):
        if self._filename is not None:
            self._file = open(self._filename, 'r')

    def close(self):
        self._file.close()

    def readsample(self):
        sample = dict()
        line = '#'
        while line[0] == '#':
            line = self._file.readline()
            if len(line) == 0:
                self._stop_sampling = True
                return None
        fields = line.split()

        data_acq = [fields[0]] + [float(val) for val in fields[1:]]

        for i, field_name in enumerate(self._file_columns):
            sample[field_name] = data_acq[i]
        return sample

    def readsamples(self, num_samples=-1):
        output = []
        go_on = num_samples
        while go_on != 0:
            output.append(self.readsample())
            go_on = go_on-1
            if output[-1] is None:
                output.pop()
                break
        return output


class ReadSensorSerial(ReadSensorAbstract):
    """
    Reads the Arduino serial port
    """
    def __init__(self, port, config):
        """
        Reads the Arduino and optionally saves a copy of the readed data to a
        file.

        Args:
            port (str): Serial port to read data from.
            timeout (int): Seconds until a read value times out

        Details:
            Each sample in the arduino is printed through the serial port
            on a single line. Fields (time, sensor readings) are separated by
            a space.
        """
        if port is None:
            raise ValueError("port missing. No input given")
        # Initialize parent class:
        super(ReadSensorSerial, self).__init__()
        # Fields:
        self._fields = []
        for column in config["arduino"]["columns"]:
            self._fields.append((column["name"], column["conversion_factor"]))
        self.port = port
        self._baudrate = config["arduino"]["baudrate"]
        self._timeout = config["arduino"]["timeout"]
        self._inputdata = None
        return

    def open(self):
        self._inputdata = serial.Serial(self.port, baudrate=self._baudrate,
                                        timeout=self._timeout)
        self._stop_sampling = False
        return

    def close(self):
        # close serial port
        self._inputdata.flush()
        self._inputdata.close()
        self._stop_sampling = True

    def readsample(self):
        # This block prevents the program to abort when initial garbage is read
        # in the serial port in Windows @soller
        sample = dict()
        try_again = True
        while try_again:
            try:
                line = self._inputdata.readline()
                try_again = False
                if len(line) == 0:
                    self._stop_sampling = True
                    break
                data_acq = [float(val) for val in line.split()]
                if len(data_acq) != len(self._fields):
                    print("Received {} fields, expecting {}.".
                          format(len(data_acq), len(self._fields)))
                    print(line)
                    try_again = True
            except (UnicodeDecodeError, ValueError):
                print("Discarding garbage in serial port")
                try_again = True

        if self._stop_sampling:
            return None
        # Convert units of acquired values and store in sample:
        for i, (field_name, factor) in enumerate(self._fields):
            sample[field_name] = data_acq[i]*factor
        sample[TIME_COMPUTER] = datetime.datetime.now().isoformat()
        return sample

    def readsamples(self, num_samples=10):
        output = []
        for _ in range(num_samples):
            output.append(self.readsample())
            if output[-1] is None:
                output.pop()
                break
        return output

class WriteSensorFile(object):
    """
    Writes samples to a file
    """
    def __init__(self, filename, config):
        """
            filename (str): File name to dump the data to.
        """
        self.filename = filename
        self._file_columns = config.get("columns", [])
        self._filepointer = None
        return

    def __enter__(self):
        "Creates file and writes header"
        if self.filename:
            mkdir_p(os.path.dirname(self.filename))
            self._filepointer = open(self.filename, 'w')
            self._filepointer.write("# %s\n" % datetime.datetime.now())
            self._filepointer.write("#" + "\t".join(self._file_columns) + "\n")
            self._filepointer.flush()
        return self

    def _write_sample(self, sample):
        """ Writes a sample to a file (columns given by file_columns)
        """
        line = "\t".join([str(sample[item]) for item in self._file_columns])
        self._filepointer.write(line + "\n")
        self._filepointer.flush()

    def __exit__(self, typ, value, traceback):
        if self._filepointer is not None:
            self._filepointer.flush()
            self._filepointer.close()
        if typ is None:
            return True
        else:
            return False

    def write(self, samples):
        if self.filename is not None:
            for sample in samples:
                self._write_sample(sample)
        return

class DataBuffers(object):
    """
    Stores the acquired data of all the sensors. It can be used to store
    only the last ``maxlen`` points, so memory is limited in long experiments.

    Args:
        maxlen (int): Keep only the latest maxlen points (default: None)
    """
    def __init__(self, maxlen=None):
        self.data = defaultdict(partial(deque, maxlen=maxlen))
        self.maxlen = maxlen

    def set_maxlen(self, maxlen=None):
        """
        Sets a new buffer size. Requires copying the buffers.
        """
        data = defaultdict(partial(deque, maxlen=maxlen))
        for (name, values) in self.data.items():
            if maxlen is None:
                data[name] = deque(values)
            else:
                values = list(values)[0:maxlen]
                data[name] = deque(values, maxlen=maxlen)
        return

    def appendleft(self, sample):
        for sensor, value in sample.items():
            self.data[sensor].appendleft(value)

    def append(self, sample):
        for sensor, value in sample.items():
            self.data[sensor].append(value)

    def extend(self, samples):
        for sample in samples:
            self.append(sample)

    def extendleft(self, samples):
        for sample in samples:
            self.appendleft(sample)

