# aves: Acquisition, Visualization and Exploration Software

This python module makes it easy to acquire data from a serial port, visualize it
on real time and record it. It also provides a module for visualizing data previously
aquired with this tool.

## Installation

    pip3 install aves

## Quick start

- We will use an Arduino to send data through the serial port.
- We will use *aves* to acquire, represent and record the data.

### Arduino code

Create a file with the contents from [example/arduino.ino](https://github.com/zeehio/aves/blob/master/example/arduino.ino).

This sample code reads the analog ports from the arduino board and prints them on the serial port.

Take note of:
- The SAMPLE_TIME (in ms): `100`
- The Serial port speed (in bauds): `9600`
- The Analog Read Resolution (in bits): `10`
- The input range of the analog ports (in volts): `(check your board, usually 5V or 3.3V)`

### Aves configuration

Aves is configured using a `yaml` file. Please take the example file from 
[example/config.yaml](https://github.com/zeehio/aves/blob/master/example/config.yaml).

The yaml file has four sections:

- `version`: Just a value, must be 2.
- `input`: Defines the aves input sources.
- `gui`: Controls the real time plotting options
- `output`: Defines the columns with sensor data that will be saved in a text file.

#### The `input` section

Aves uses two sources of information, the *arduino* and the *computer clock*.

For the arduino input, we have multiple parameters:

- `baudrate`: The baudrate specified in the arduino code.
- `timeout`: The seconds the python code will wait for data until it believes the serial connection has been dropped.
- `columns`: Aves must know what is the arduino printing on the serial port. `columns` is a list with as many elements as columns.
    Each element is defined by `name` which gives a name to the column and `conversion_factor` that is used to convert the
    number printed by the arduino to a magnitude meaninful for us. For instance, the conversion_factor is used in the example
    to convert the time printed by the arduino from milliseconds to seconds (0.001), and the sensor reads (in the range 0-1023) to Volts
    (in the range 0-5V): (5V/1023 = 0.004887586). The columns should be given in the order that they are printed by the arduino.

The computer clock does not have an entry, as it has no options. However, we should remember that besides the columns defined
in the `arduino` section, we also have the `time_computer` column, useful to synchronize our experiment with other information.


#### The `gui` section

The `gui` defines the visualization options, including:

- The name of the column used in the `x` axis (`x_column`). It usually is the time given by the Arduino.
- Whether or not the zoom for all the subplots should be shared. It is often convenient to have it shared (`zoom_all_together`).
- The `axes`: The subplots available in the window. Imagine the subplots layed out in a grid. The first subplot (top-left) would be
  in `row: 0`, `col: 0`. The subplot below the first would appear in `row: 1`, `col: 0`, etc. Subplots may span several rows or columns,
  to make them larger, with the `rowspan` and `colspan` options, by default both set to `1`. Each subplot should plot at least one column
  from the input, although more than one column can be plotted. The column names to be plotted for each subplot are given in `columns`.
  Additional plotting options (limits, labels) can be given in `options`.

Besides, there is the name of the window `window_title` and the `refresh_time_ms` that controls how often the GUI is refreshed.

#### The `output` section

Controls the columns that will be printed to the text file. Note how we have in the example 
both the computer time and the arduino time printed.


### Run it:

    python3 -m aves.realtime --port *Serial port where your arduino is connected* --outfile "test.txt"

Check `python3 -m aves.realtime --help` for all other command line options, for instance:

- `--no-save` Do not save the captured data to a file
- `--outfile test.txt` Save the capture data to `test.txt`
- `--tmeas 600` Capture data for 600 seconds maximum (default: unlimited)
- `--port COM3` Use the `COM3` serial port
- `--plot_every_n_samples 10` Wait for at least 10 samples to refresh the GUI
- `--plot_win_size 200` Keep up to 200 samples in the plot (use 0 for unlimited)
- `--config another.yaml` Use `another.yaml` as config file.

![Image of the acquisition demo](example/demo.png)

### Explore the acquired data:

    python3 -m aves.explorer --filename "test.txt"


## Known works using aves

- The prototype for fire detection developed at IBEC under the SafeSens project
