/*
  =============================================================================
  CONSTRUCTION SITE SAFETY MONITORING SYSTEM - ARDUINO GATE CONTROLLER
  =============================================================================
  Hardware Components:
  - Arduino Uno
  - IR Sensor (Obstacle / Entry detection)
  - Ultrasonic Sensor (HC-SR04 for Proximity / Danger Zone check)
  - Buzzer (Active or Passive Buzzer)
  - 16x2 LCD Display (Supports either I2C or 4-bit Parallel)
  - Breadboard & Jumper wires

  PIN CONNECTIONS:
  -----------------------------------------------------------------------------
  1. IR Sensor:
     - VCC  -> 5V
     - GND  -> GND
     - OUT  -> Arduino Digital Pin 7

  2. Ultrasonic Sensor (HC-SR04):
     - VCC  -> 5V
     - GND  -> GND
     - TRIG -> Arduino Digital Pin 9
     - ECHO -> Arduino Digital Pin 8

  3. Buzzer:
     - Positive (+) -> Arduino Digital Pin 10
     - Negative (-) -> GND

  4. LCD 16x2 (I2C Mode - Recommended for breadboard with fewer wires):
     - VCC -> 5V
     - GND -> GND
     - SDA -> Arduino A4
     - SCL -> Arduino A5

     * If using Parallel 4-bit LCD (No I2C backpack), set USE_I2C_LCD to 0:
       RS -> Pin 12, E -> Pin 11, D4 -> Pin 5, D5 -> Pin 4, D6 -> Pin 3, D7 -> Pin 2
  =============================================================================
*/

// Set to 1 if using I2C LCD Backpack (0x27 or 0x3F), or 0 for standard 6-pin parallel LCD
#define USE_I2C_LCD 1

#if USE_I2C_LCD
  #include <Wire.h>
  #include <LiquidCrystal_I2C.h>
  // Common I2C addresses are 0x27 or 0x3F
  LiquidCrystal_I2C lcd(0x27, 16, 2);
#else
  #include <LiquidCrystal.h>
  // RS, E, D4, D5, D6, D7
  LiquidCrystal lcd(12, 11, 5, 4, 3, 2);
#endif

// Pin Definitions
const int PIN_IR_SENSOR   = 7;
const int PIN_US_TRIG     = 9;
const int PIN_US_ECHO     = 8;
const int PIN_BUZZER      = 10;

// Variables
long lastTelemetryTime = 0;
const long TELEMETRY_INTERVAL = 150; // Send sensor updates every 150ms

String inputString = "";
bool stringComplete = false;

// Buzzer state
int currentBuzzerPattern = 0;
unsigned long buzzerStartTime = 0;

void setup() {
  // Initialize Serial at 9600 baud for Python communication
  Serial.begin(9600);
  inputString.reserve(100);

  // Pin Modes
  pinMode(PIN_IR_SENSOR, INPUT);
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize LCD
  #if USE_I2C_LCD
    lcd.init();
    lcd.backlight();
  #else
    lcd.begin(16, 2);
  #endif

  // Welcome Screen
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SITE SAFETY GATE");
  lcd.setCursor(0, 1);
  lcd.print("SYSTEM READY...");

  // Quick power-on beep
  digitalWrite(PIN_BUZZER, HIGH);
  delay(120);
  digitalWrite(PIN_BUZZER, LOW);
}

void loop() {
  // 1. Check for commands from Python
  if (stringComplete) {
    handleCommand(inputString);
    inputString = "";
    stringComplete = false;
  }

  // 2. Read Sensors and send telemetry periodically
  unsigned long now = millis();
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL) {
    lastTelemetryTime = now;
    readSensorsAndSend();
  }

  // 3. Handle Buzzer Timing
  handleBuzzer();
}

// Measure Ultrasonic Distance in centimeters
float measureDistance() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);

  long duration = pulseIn(PIN_US_ECHO, HIGH, 25000); // 25ms timeout (~4 meters)
  if (duration == 0) {
    return 200.0; // Out of range or no echo
  }
  float dist = (duration * 0.0343) / 2.0;
  return dist;
}

// Reads IR and Ultrasonic, formats as clean JSON
void readSensorsAndSend() {
  // Most digital IR obstacle sensors read LOW when an obstacle is detected
  int irRaw = digitalRead(PIN_IR_SENSOR);
  int irDetected = (irRaw == LOW) ? 1 : 0; // Inverted for active-low IR sensors

  float distance = measureDistance();

  // Send JSON line over serial: {"ir":1,"dist":34.2}
  Serial.print("{\"ir\":");
  Serial.print(irDetected);
  Serial.print(",\"dist\":");
  Serial.print(distance, 1);
  Serial.println("}");
}

// Handles commands from Python
// Format: CMD:ACTION|LINE1|LINE2|BUZZER_PATTERN
void handleCommand(String cmd) {
  cmd.trim();
  if (!cmd.startsWith("CMD:")) return;

  String payload = cmd.substring(4);
  int firstPipe = payload.indexOf('|');
  int secondPipe = payload.indexOf('|', firstPipe + 1);
  int thirdPipe = payload.indexOf('|', secondPipe + 1);

  if (firstPipe == -1 || secondPipe == -1 || thirdPipe == -1) return;

  String action = payload.substring(0, firstPipe);
  String line1  = payload.substring(firstPipe + 1, secondPipe);
  String line2  = payload.substring(secondPipe + 1, thirdPipe);
  int buzzerPat = payload.substring(thirdPipe + 1).toInt();

  // Update LCD Display
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));

  // Trigger Buzzer pattern
  currentBuzzerPattern = buzzerPat;
  buzzerStartTime = millis();

  if (currentBuzzerPattern == 1) {
    // Short confirmation beep (Access Granted)
    digitalWrite(PIN_BUZZER, HIGH);
  } else if (currentBuzzerPattern == 2) {
    // Alarm pulse start (Access Denied / Violation)
    digitalWrite(PIN_BUZZER, HIGH);
  } else if (currentBuzzerPattern == 3) {
    // Hazard continuous
    digitalWrite(PIN_BUZZER, HIGH);
  } else {
    digitalWrite(PIN_BUZZER, LOW);
  }
}

// Manage non-blocking buzzer patterns
void handleBuzzer() {
  if (currentBuzzerPattern == 0) {
    digitalWrite(PIN_BUZZER, LOW);
    return;
  }

  unsigned long elapsed = millis() - buzzerStartTime;

  if (currentBuzzerPattern == 1) {
    // 1 beep (180ms)
    if (elapsed >= 180) {
      digitalWrite(PIN_BUZZER, LOW);
      currentBuzzerPattern = 0;
    }
  } else if (currentBuzzerPattern == 2) {
    // 3 rapid warning beeps (600ms total)
    if (elapsed < 120) digitalWrite(PIN_BUZZER, HIGH);
    else if (elapsed < 200) digitalWrite(PIN_BUZZER, LOW);
    else if (elapsed < 320) digitalWrite(PIN_BUZZER, HIGH);
    else if (elapsed < 400) digitalWrite(PIN_BUZZER, LOW);
    else if (elapsed < 520) digitalWrite(PIN_BUZZER, HIGH);
    else {
      digitalWrite(PIN_BUZZER, LOW);
      currentBuzzerPattern = 0;
    }
  } else if (currentBuzzerPattern == 3) {
    // Hazard proximity pulsing
    if (elapsed % 300 < 150) {
      digitalWrite(PIN_BUZZER, HIGH);
    } else {
      digitalWrite(PIN_BUZZER, LOW);
    }
    // Stop after 2 seconds unless refreshed
    if (elapsed > 2000) {
      digitalWrite(PIN_BUZZER, LOW);
      currentBuzzerPattern = 0;
    }
  }
}

// Serial Event listener
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}
