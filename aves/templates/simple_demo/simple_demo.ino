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

