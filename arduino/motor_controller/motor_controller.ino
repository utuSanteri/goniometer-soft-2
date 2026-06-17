/*
 * motor_controller_accel.ino
 * ─────────────────────────────────────────────────────────────────────
 * Controls two step/dir stepper motor drivers from an Arduino Nano
 * using the AccelStepper library.
 * * Serial protocol remains identical to the original specification.
 * ─────────────────────────────────────────────────────────────────────
 */

#include <AccelStepper.h>

// ── Pin Definitions ──────────────────────────────────────────────────
#define M1_STEP_PIN   2
#define M1_DIR_PIN    3
#define M2_STEP_PIN   4
#define M2_DIR_PIN    5
#define M1_EN_PIN     6
#define M2_EN_PIN     7

// ── Globals ──────────────────────────────────────────────────────────
// Initialize AccelStepper objects in step/dir mode (DRIVER)
AccelStepper stepper1(AccelStepper::DRIVER, M1_STEP_PIN, M1_DIR_PIN);
AccelStepper stepper2(AccelStepper::DRIVER, M2_STEP_PIN, M2_DIR_PIN);

// State tracking to handle asynchronous "OK" replies
enum MotionState { IDLE, WAIT_M1, WAIT_M2, WAIT_HOME };
MotionState currentMotion = IDLE;

// ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // Configure Enable pins (active LOW is standard for drivers like A4988/TMC2209)
  stepper1.setEnablePin(M1_EN_PIN);
  stepper1.setPinsInverted(false, false, true); // (dir, step, enable)
  stepper1.enableOutputs();

  stepper2.setEnablePin(M2_EN_PIN);
  stepper2.setPinsInverted(false, false, true);
  stepper2.enableOutputs();

  // Default speed and acceleration profiles
  stepper1.setMaxSpeed(200.0);
  stepper1.setAcceleration(1000.0); 
  stepper2.setMaxSpeed(200.0);
  stepper2.setAcceleration(1000.0);

  Serial.println("READY");
}

// ─────────────────────────────────────────────────────────────────────
void loop() {
  // Service motor step generation
  stepper1.run();
  stepper2.run();

  // Handle serial reporting for completed motions
  checkMotionCompletion();

  // Process incoming commands
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      handleCommand(line);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────
void checkMotionCompletion() {
  if (currentMotion == IDLE) return;

  bool m1Done = (stepper1.distanceToGo() == 0);
  bool m2Done = (stepper2.distanceToGo() == 0);

  if (currentMotion == WAIT_M1 && m1Done) {
    Serial.println("OK");
    currentMotion = IDLE;
  } 
  else if (currentMotion == WAIT_M2 && m2Done) {
    Serial.println("OK");
    currentMotion = IDLE;
  } 
  else if (currentMotion == WAIT_HOME && m1Done && m2Done) {
    Serial.println("OK");
    currentMotion = IDLE;
  }
}

// ─────────────────────────────────────────────────────────────────────
void handleCommand(String cmd) {
  if (cmd.startsWith("MOVE")) {
    int m, steps, dir;
    if (sscanf(cmd.c_str(), "MOVE %d %d %d", &m, &steps, &dir) == 3) {
      long targetSteps = (dir == 1) ? steps : -steps;
      if (m == 1) {
        stepper1.move(targetSteps);
        currentMotion = WAIT_M1;
      } else if (m == 2) {
        stepper2.move(targetSteps);
        currentMotion = WAIT_M2;
      }
    } else {
      Serial.println("ERR invalid MOVE syntax");
    }

  } else if (cmd.startsWith("SPEED")) {
      int spd; // Change to int
      // Parse using %d instead of %f
      if (sscanf(cmd.c_str(), "SPEED %d", &spd) == 1 && spd > 0) { 
        stepper1.setMaxSpeed((float)spd); // Cast to float for AccelStepper
        stepper2.setMaxSpeed((float)spd);
        Serial.println("OK");
      } else {
        Serial.println("ERR invalid SPEED syntax");
      }

  } else if (cmd == "STOP") {
    // Calculates a new target position that stops the motor as quickly as possible
    stepper1.stop();
    stepper2.stop();
    Serial.println("OK");
    currentMotion = IDLE;

  } else if (cmd == "HOME") {
    stepper1.moveTo(0);
    stepper2.moveTo(0);
    currentMotion = WAIT_HOME;

  } else if (cmd == "ZERO") {
    stepper1.setCurrentPosition(0);
    stepper2.setCurrentPosition(0);
    Serial.println("OK");

  } else if (cmd == "STATUS") {
    Serial.print("POS ");
    Serial.print(stepper1.currentPosition());
    Serial.print(" ");
    Serial.println(stepper2.currentPosition());

  } else if (cmd == "PING") {
    Serial.println("PONG");

  } else {
    Serial.println("ERR unknown command");
  }
}