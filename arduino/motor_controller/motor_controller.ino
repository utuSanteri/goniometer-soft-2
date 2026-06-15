/*
 * motor_controller.ino
 * ─────────────────────────────────────────────────────────────────────
 * Controls two step/dir stepper motor drivers from an Arduino Nano.
 *
 * Serial protocol (115200 baud, newline-terminated):
 *
 *  MOVE <motor> <steps> <dir>
 *      motor : 1 or 2
 *      steps : integer number of steps
 *      dir   : 0 or 1
 *      reply : "OK\n" when motion complete
 *
 *  SPEED <steps_per_sec>
 *      Sets step pulse rate (applies to both motors)
 *      reply : "OK\n"
 *
 *  STOP
 *      Immediately halt all motion
 *      reply : "OK\n"
 *
 *  HOME
 *      Drive both motors to position 0 (software zero)
 *      reply : "OK\n"
 *
 *  ZERO
 *      Set current position as zero for both motors
 *      reply : "OK\n"
 *
 *  STATUS
 *      reply : "POS <pos1> <pos2>\n"
 *
 *  PING
 *      reply : "PONG\n"
 * ─────────────────────────────────────────────────────────────────────
 */

// ── Pin Definitions ──────────────────────────────────────────────────
#define M1_STEP_PIN   2
#define M1_DIR_PIN    3
#define M2_STEP_PIN   4
#define M2_DIR_PIN    5

// Optional enable pin (LOW = enabled on most drivers)
#define M1_EN_PIN     6
#define M2_EN_PIN     7

// ── Globals ──────────────────────────────────────────────────────────
volatile bool stopFlag = false;

long pos1 = 0;   // software position tracking (steps)
long pos2 = 0;

unsigned int stepPulseUs   = 50;     // step HIGH pulse width
unsigned long stepPeriodUs = 5000;    // full period between steps (~200 steps/s)

// ─────────────────────────────────────────────────────────────────────
void setup() {
  pinMode(M1_STEP_PIN, OUTPUT);
  pinMode(M1_DIR_PIN,  OUTPUT);
  pinMode(M2_STEP_PIN, OUTPUT);
  pinMode(M2_DIR_PIN,  OUTPUT);
  pinMode(M1_EN_PIN,   OUTPUT);
  pinMode(M2_EN_PIN,   OUTPUT);

  // Enable drivers
  digitalWrite(M1_EN_PIN, LOW);
  digitalWrite(M2_EN_PIN, LOW);

  // Safe initial state
  digitalWrite(M1_STEP_PIN, LOW);
  digitalWrite(M2_STEP_PIN, LOW);

  Serial.begin(115200);
  Serial.println("READY");
}

// ─────────────────────────────────────────────────────────────────────
void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    handleCommand(line);
  }
}

// ─────────────────────────────────────────────────────────────────────
void handleCommand(String cmd) {
  if (cmd.startsWith("MOVE")) {
    // MOVE <motor> <steps> <dir>
    int m, steps, dir;
    sscanf(cmd.c_str(), "MOVE %d %d %d", &m, &steps, &dir);
    stopFlag = false;
    doMove(m, steps, (bool)dir);
    Serial.println("OK");

  } else if (cmd.startsWith("SPEED")) {
    unsigned long spd;
    sscanf(cmd.c_str(), "SPEED %lu", &spd);
    if (spd > 0) {
      stepPeriodUs = 1000000UL / spd;
      if (stepPeriodUs < (unsigned long)(stepPulseUs * 2))
        stepPeriodUs = (unsigned long)(stepPulseUs * 2);
    }
    Serial.println("OK");

  } else if (cmd == "STOP") {
    stopFlag = true;
    Serial.println("OK");

  } else if (cmd == "HOME") {
    // Drive back to position zero
    stopFlag = false;
    goHome(1);
    goHome(2);
    Serial.println("OK");

  } else if (cmd == "ZERO") {
    pos1 = 0;
    pos2 = 0;
    Serial.println("OK");

  } else if (cmd == "STATUS") {
    Serial.print("POS ");
    Serial.print(pos1);
    Serial.print(" ");
    Serial.println(pos2);

  } else if (cmd == "PING") {
    Serial.println("PONG");

  } else {
    Serial.println("ERR unknown command");
  }
}

// ─────────────────────────────────────────────────────────────────────
void doMove(int motor, int steps, bool direction) {
  uint8_t stepPin = (motor == 1) ? M1_STEP_PIN : M2_STEP_PIN;
  uint8_t dirPin  = (motor == 1) ? M1_DIR_PIN  : M2_DIR_PIN;

  digitalWrite(dirPin, direction ? HIGH : LOW);
  delayMicroseconds(5);   // dir setup time

  for (int i = 0; i < steps; i++) {
    if (stopFlag) break;

    digitalWrite(stepPin, HIGH);
    delayMicroseconds(stepPulseUs);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(stepPeriodUs - stepPulseUs);

    // Track position
    if (motor == 1) pos1 += (direction ? 1 : -1);
    else            pos2 += (direction ? 1 : -1);
  }
}

// ─────────────────────────────────────────────────────────────────────
void goHome(int motor) {
  long* pos = (motor == 1) ? &pos1 : &pos2;
  if (*pos == 0) return;

  bool dir = (*pos < 0);   // go opposite direction of offset
  long steps = abs(*pos);
  doMove(motor, (int)steps, dir);
}