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

Reads the analog ports from the arduino board and prints them on the serial port:

```
#include "Arduino.h"

/* Sample time and serial port speed */
/* ================================= */
const uint32_t SAMPLE_TIME =  100UL; /* ms */
const int SERIAL_PORT_BAUDS = 9600; /* bauds */

unsigned long prevMillis = 0;

void setup()
{

  Serial.begin(SERIAL_PORT_BAUDS);
  analogReadResolution(10); /* 10 bits => 2^10 = 1024 levels in analogRead() */
}

void loop() {
  unsigned long curMillis = millis();

  if (curMillis - prevMillis >= SAMPLE_TIME) {
    int sensor1 = analogRead(A0);
    int sensor2 = analogRead(A1);
    /* Check your Arduino specs:
     * - The input range on the analog ports
     * - The resolution (set above, some boards have 12 bits ADC capabilities)
     * analogRead maps voltage from the input range (usually [0, 5] or [0, 3.3] volts)
     * to integer values in the range [0, 1023] or [0, 4095] (depends on the resolution)
     */
    Serial.print(millis());
    Serial.print(" ");
    Serial.print(sensor1);
    Serial.print(" ");
    Serial.print(sensor2);
    Serial.print("\n");
    prevMillis = curMillis;
  }
}
```

Take note of:
- The SAMPLE_TIME (in ms): `100`
- The Serial port speed (in bauds): `9600`
- The Analog Read Resolution (in bits): `10`
- The input range of the analog ports (in volts): `(check your board, usually 5V or 3.3V)`

### Aves configuration

Aves is configured using a `json` file. Save it as `config.json`.

- The `arduino` section:
  * `baudrate`: The same as the arduino code.
  * `timeout`: the seconds the python code will wait for data until it believes the serial connection has been dropped.
  * `columns`: Describes the printed columns in the same order than in the arduino code. The conversion_factor is used to convert
               the time from the arduino from milliseconds to seconds, and the sensor reads to Volts ( 5V/1023 = 0.004887586)
- The `gui` defines the `axes` or subplots, and where will be placed. Each subplot sets which `points` from the captured data will contain.

```
{
  "version": 1,
  "input": {
    "time_python": "time_python",
    "arduino": {
      "baudrate": 9600,
      "timeout": 3,
      "columns": [
        {
          "point": "time_arduino",
          "conversion_factor": 1E-3
        },
        {
          "point": "Sensor 1",
          "conversion_factor": 0.004887586
        },
        {
          "point": "Sensor 2",
          "conversion_factor": 0.004887586
        }
      ]
    }
  },
  "gui": {
    "window_title": "Aves Demo",
    "refresh_time_ms": 100,
    "axes": {
      "A subplot": {
        "row": 0,
        "col": 0,
        "rowspan": 1,
        "colspan": 1,
        "points": ["Sensor 1"],
        "options": {
          "ylim": [-0.5, 5.5],
          "ylabel": "Sensor 1 (V)"
        }
      },
      "Another subplot": {
        "row": 2,
        "col": 0,
        "rowspan": 1,
        "colspan": 1,
        "points": ["Sensor 2"],
        "options": {
          "ylim": [-0.5, 5.5],
          "ylabel": "Sensor 2 (V)"
        }
      }
    },
   "sharexaxis": true,
   "x_points": "time_arduino"
  },
  "output" : {
    "columns": [
      "time_python", "time_arduino", "Sensor 1", "Sensor 2"
    ]
  }
}
```
### Run it:

    python3 -m aves.realtime --port *Serial port where your arduino is connected* --outfile "test.txt"

Check `python3 -m aves.realtime --help` for all other command line options, for instance:

- `--no-save` Do not save the captured data to a file
- `--outfile test.txt` Save the capture data to `test.txt`
- `--tmeas 600` Capture data for 600 seconds maximum (default: unlimited)
- `--port COM3` Use the `COM3` serial port
- `--plot_every_n_samples 10` Wait for at least 10 samples to refresh the GUI
- `--plot_win_size 200` Keep up to 200 samples in the plot (use 0 for unlimited)
- `--config another.json` Use `another.json` as config file.

![Image of the acquisition demo](example/demo.png)

### Explore the acquired data:

    python3 -m aves.explorer --filename "test.txt"


## Known works using aves

- The prototype for fire detection developed at IBEC under the SafeSens project
