//
// パラメーター
//

// ボーレート
const unsigned long BAUD = 115200;

// 出力ピン
const int CENTER_FAN_PIN = 2;
const int CENTER_LED_RED_PIN = 3;
const int CENTER_LED_YELLOW_PIN = 4;
const int CENTER_LED_GREEN_PIN = 5;
const int CENTER_LED_BLUE_PIN = 6;
const int SIDE_FAN_PIN = 7;
const int SIDE_LED_RED_PIN = 8;
const int SIDE_LED_YELLOW_PIN = 9;
const int SIDE_LED_GREEN_PIN = 10;
const int SIDE_LED_BLUE_PIN = 11;

// ゲーミングの周期
const float gaming_period = 1.0;

// 点滅の周期
const float blink_period = 0.2;

// 炎上レベルの範囲
const int MIN_DISPLAY_LEVEL = -4;
const int MAX_DISPLAY_LEVEL = 3;

//
// 状態変数
//

// 表示する炎上レベル
int display_level = 0;
// 前に表示を更新したときの炎上レベル
int prev_display_level = 0;

float prev_clock = 0;
float clock = 0;

// ゲーミングが、周期の中のどこか
float gaming_time = 0;

// 点滅が、周期の中のどこか
float blink_time = 0;

void setup() {
  Serial.begin(BAUD);
  pinMode(CENTER_FAN_PIN, OUTPUT);
  pinMode(CENTER_LED_RED_PIN, OUTPUT);
  pinMode(CENTER_LED_YELLOW_PIN, OUTPUT);
  pinMode(CENTER_LED_GREEN_PIN, OUTPUT);
  pinMode(CENTER_LED_BLUE_PIN, OUTPUT);
  pinMode(SIDE_FAN_PIN, OUTPUT);
  pinMode(SIDE_LED_RED_PIN, OUTPUT);
  pinMode(SIDE_LED_YELLOW_PIN, OUTPUT);
  pinMode(SIDE_LED_GREEN_PIN, OUTPUT);
  pinMode(SIDE_LED_BLUE_PIN, OUTPUT);

  prev_clock = millis() / 1000.0;
  clock = millis() / 1000.0;
}

void clearDisplay() {
  digitalWrite(CENTER_FAN_PIN, LOW);
  digitalWrite(CENTER_LED_RED_PIN, LOW);
  digitalWrite(CENTER_LED_YELLOW_PIN, LOW);
  digitalWrite(CENTER_LED_GREEN_PIN, LOW);
  digitalWrite(CENTER_LED_BLUE_PIN, LOW);
  digitalWrite(SIDE_FAN_PIN, LOW);
  digitalWrite(SIDE_LED_RED_PIN, LOW);
  digitalWrite(SIDE_LED_YELLOW_PIN, LOW);
  digitalWrite(SIDE_LED_GREEN_PIN, LOW);
  digitalWrite(SIDE_LED_BLUE_PIN, LOW);
}

// 今回の周期で、設定すべき炎上レベルを取得する
void updateDisplayLevel() {
  display_level = 2;

  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  int level;
  level = line.toInt();
  level = constrain(level, MIN_DISPLAY_LEVEL, MAX_DISPLAY_LEVEL);
  display_level = level;
}

// 炎上レベルに応じて、光り方や変数の更新を行う
void applyDisplayLevel() {
  if (display_level == -4 || display_level == -3 || display_level == -2 || display_level == -1) {
    blink_time = 0;
  } else if (display_level == 0) {

  } else if (display_level == 1) {

  } else if (display_level == 2) {

  } else if (display_level == 3) {
    gaming_time = 0;
  }
  clearDisplay();
}

// 毎周期必要な、表示の更新を行う
void updateDisplay() {
  if (display_level == -4 || display_level == -3 || display_level == -2 || display_level == -1) {
    if (blink_time > blink_period) {
      blink_time = 0;
    }
    bool is_led_high = (blink_time < blink_period / 2);

    int led_pin;
    if (display_level == -4) {
      led_pin = CENTER_LED_RED_PIN;
    } else if (display_level == -3) {
      led_pin = CENTER_LED_YELLOW_PIN;
    } else if (display_level == -2) {
      led_pin = CENTER_LED_GREEN_PIN;
    } else if (display_level == -3) {
      led_pin = CENTER_LED_BLUE_PIN;
    }

    if (is_led_high) {
      digitalWrite(led_pin, HIGH);
    } else {
      digitalWrite(led_pin, LOW);
    }
  } else if (display_level == 0) {

  } else if (display_level == 1) {
    digitalWrite(CENTER_FAN_PIN, HIGH);
    digitalWrite(CENTER_LED_YELLOW_PIN, HIGH);
  } else if (display_level == 2) {
    digitalWrite(CENTER_FAN_PIN, HIGH);
    digitalWrite(CENTER_LED_RED_PIN, HIGH);
    digitalWrite(SIDE_FAN_PIN, HIGH);
    digitalWrite(SIDE_LED_RED_PIN, HIGH);
  } else if (display_level == 3) {
    // あとでゲーミングを書く
  }
}

void loop() {
  prev_clock = clock;
  clock = millis() / 1000.0;
  float dt = clock - prev_clock;
  // Serial.println("###");
  // Serial.println(prev_clock);
  // Serial.println(clock);
  blink_time += dt;
  gaming_time += dt;
  updateDisplayLevel();
  if (prev_display_level != display_level) {
    prev_display_level = display_level;
    applyDisplayLevel();
  }
  updateDisplay();
}
