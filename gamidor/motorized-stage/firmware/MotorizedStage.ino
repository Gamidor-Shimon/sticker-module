/*
 * Gamidor Motorized Stage Firmware
 * ESP32 DevKit V1 + TMC2209 + NEMA 17 (17HS3401) + Optical endstop
 *
 * Serial API @ 115200:
 *   INIT          -> homing (reverse only) -> "HOME_DONE"
 *   POS1          -> move to TARGET_POS1
 *   POS2          -> move to TARGET_POS2
 *   GOTO <abs>    -> move to absolute step <abs>
 *   SPEED <v>     -> set max speed (steps/sec)
 * Feedback: "BUSY" on accept, "DONE" on target reached, "ERR <msg>" on bad input.
 */

#include <AccelStepper.h>

// ---- Pinout (immutable per hardware spec) ----
constexpr uint8_t PIN_EN       = 26;   // TMC2209 EN, active LOW
constexpr uint8_t PIN_DIR      = 27;   // TMC2209 DIR
constexpr uint8_t PIN_STEP     = 14;   // TMC2209 STEP
constexpr uint8_t PIN_ENDSTOP  = 32;   // Optical endstop signal

// ---- Endstop logic (set easily) ----
// If endstop pulls signal LOW when triggered -> ENDSTOP_TRIGGERED_LEVEL = LOW
// Use INPUT_PULLUP when sensor is open-collector style.
constexpr uint8_t  ENDSTOP_PIN_MODE          = INPUT_PULLUP;
constexpr uint8_t  ENDSTOP_TRIGGERED_LEVEL   = LOW;

// ---- Motion defaults ----
constexpr long  DEFAULT_MAX_SPEED   = 1000;   // steps/sec
constexpr long  DEFAULT_ACCEL       = 1500;   // steps/sec^2
constexpr long  HOMING_SPEED        = 600;    // steps/sec while seeking home
constexpr long  HOMING_BACKOFF      = 80;     // steps to back off after hit
constexpr long  TARGET_POS1         = 2000;
constexpr long  TARGET_POS2         = 6000;

// ---- Driver objects ----
AccelStepper stepper(AccelStepper::DRIVER, PIN_STEP, PIN_DIR);

// ---- State ----
enum class Mode { IDLE, HOMING_SEEK, HOMING_BACKOFF_STATE, MOVING };
Mode mode = Mode::IDLE;
bool homed = false;
String rxBuf;

// ---- Helpers ----
inline bool endstopTriggered() {
  return digitalRead(PIN_ENDSTOP) == ENDSTOP_TRIGGERED_LEVEL;
}

void enableDriver(bool on) {
  digitalWrite(PIN_EN, on ? LOW : HIGH); // active LOW
}

void startMoveAbs(long absTarget) {
  if (!homed) {
    Serial.println("ERR NOT_HOMED");
    return;
  }
  stepper.moveTo(absTarget);
  mode = Mode::MOVING;
  Serial.println("BUSY");
}

void startHoming() {
  // Always move in NEGATIVE direction to find sensor. Never wrap forward.
  enableDriver(true);
  stepper.setMaxSpeed(HOMING_SPEED);
  stepper.setAcceleration(DEFAULT_ACCEL);
  // Use a far negative target; stop on sensor.
  stepper.moveTo(-2000000000L);
  mode = Mode::HOMING_SEEK;
  homed = false;
  Serial.println("BUSY");
}

void handleHomingSeek() {
  if (endstopTriggered()) {
    stepper.stop();          // decelerate to stop
    stepper.setCurrentPosition(stepper.currentPosition()); // freeze
    // Back off in positive direction a few steps to release sensor
    stepper.moveTo(stepper.currentPosition() + HOMING_BACKOFF);
    mode = Mode::HOMING_BACKOFF_STATE;
    return;
  }
  stepper.run();
}

void handleHomingBackoff() {
  if (stepper.distanceToGo() == 0) {
    stepper.setCurrentPosition(0);            // absolute zero
    stepper.setMaxSpeed(DEFAULT_MAX_SPEED);
    stepper.setAcceleration(DEFAULT_ACCEL);
    homed = true;
    mode = Mode::IDLE;
    Serial.println("HOME_DONE");
    return;
  }
  stepper.run();
}

void handleMoving() {
  if (stepper.distanceToGo() == 0) {
    mode = Mode::IDLE;
    Serial.println("DONE");
    return;
  }
  stepper.run();
}

void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  String upper = cmd; upper.toUpperCase();

  if (mode != Mode::IDLE && upper != "STOP") {
    Serial.println("ERR BUSY");
    return;
  }

  if (upper == "INIT") {
    startHoming();
  } else if (upper == "POS1") {
    startMoveAbs(TARGET_POS1);
  } else if (upper == "POS2") {
    startMoveAbs(TARGET_POS2);
  } else if (upper.startsWith("GOTO ")) {
    long v = cmd.substring(5).toInt();
    startMoveAbs(v);
  } else if (upper.startsWith("SPEED ")) {
    long v = cmd.substring(6).toInt();
    if (v <= 0) { Serial.println("ERR BAD_SPEED"); return; }
    stepper.setMaxSpeed(v);
    Serial.print("OK SPEED ");
    Serial.println(v);
  } else {
    Serial.println("ERR UNKNOWN");
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      processCommand(rxBuf);
      rxBuf = "";
    } else {
      rxBuf += c;
      if (rxBuf.length() > 64) rxBuf = ""; // safety
    }
  }
}

void setup() {
  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);   // start disabled
  pinMode(PIN_ENDSTOP, ENDSTOP_PIN_MODE);

  Serial.begin(115200);
  delay(50);

  stepper.setMaxSpeed(DEFAULT_MAX_SPEED);
  stepper.setAcceleration(DEFAULT_ACCEL);
  enableDriver(true);

  Serial.println("READY");
}

void loop() {
  readSerial();
  switch (mode) {
    case Mode::IDLE:                                       break;
    case Mode::HOMING_SEEK:           handleHomingSeek();  break;
    case Mode::HOMING_BACKOFF_STATE:  handleHomingBackoff(); break;
    case Mode::MOVING:                handleMoving();      break;
  }
}
