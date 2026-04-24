/**
 * Flame toy demo: reads lines "FLAME 7" from PC serial, blinks built-in LED.
 * Set SERIAL_PORT and SERIAL_SIMPLE=1 in backend/.env, baud 115200.
 */
const unsigned long BAUD = 115200;
const int LED_PIN = LED_BUILTIN;

void setup() {
  Serial.begin(BAUD);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  if (!Serial.available()) {
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.startsWith("FLAME ")) {
    int score = line.substring(6).toInt();
    score = constrain(score, 1, 10);
    int cycles = 12 - score;
    for (int i = 0; i < cycles; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(80);
      digitalWrite(LED_PIN, LOW);
      delay(80);
    }
  }
}
