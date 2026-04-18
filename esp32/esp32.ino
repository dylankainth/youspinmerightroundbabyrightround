/*
  ESP32-S3 + L298N Motor Driver
  Control motor speed via serial terminal (0-255)

  L298N Pinout:
  - IN1: Forward direction control
  - IN2: Reverse direction control
  - Enable (ENA): PWM speed control
*/

// Motor control pins
const int MOTOR_IN1 = 10;   // Forward direction
const int MOTOR_IN2 = 11;   // Reverse direction
const int MOTOR_ENABLE = 9; // PWM speed control (0-255)

// Motor state
int currentSpeed = 0;

void setup()
{
    // Initialize serial communication
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n=== ESP32-S3 Motor/Speed Control ===");
    Serial.println("Enter a number 0-255 to set motor speed");
    Serial.println("Speed 0 = stop");
    Serial.println("Speed 1-127 = rotate CW (slow to medium)");
    Serial.println("Speed 128-255 = rotate CCW (medium to fast)");
    Serial.println("=====================================\n");

    // Configure motor pins
    pinMode(MOTOR_IN1, OUTPUT);
    pinMode(MOTOR_IN2, OUTPUT);
    pinMode(MOTOR_ENABLE, OUTPUT);

    // Start with motor stopped
    setMotorSpeed(0);
}

void loop()
{
    // Check for serial input
    if (Serial.available())
    {
        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.length() > 0)
        {
            // Try to parse as integer
            int speed = input.toInt();

            // Validate range
            if (speed >= 0 && speed <= 255)
            {
                setMotorSpeed(speed);
                Serial.print("Speed set to: ");
                Serial.println(speed);
            }
            else
            {
                Serial.print("Invalid speed '");
                Serial.print(input);
                Serial.println("'. Please enter 0-255");
            }
        }
    }

    delay(10);
}

void setMotorSpeed(int speed)
{
    currentSpeed = speed;

    if (speed == 0)
    {
        // Stop motor
        digitalWrite(MOTOR_IN1, LOW);
        digitalWrite(MOTOR_IN2, LOW);
        analogWrite(MOTOR_ENABLE, 0);
        Serial.println("[Motor] STOPPED");
    }
    else if (speed <= 127)
    {
        // Forward direction (CW) - speed increases from 0 to 255
        int pwmValue = map(speed, 1, 127, 10, 255);
        digitalWrite(MOTOR_IN1, HIGH);
        digitalWrite(MOTOR_IN2, LOW);
        analogWrite(MOTOR_ENABLE, pwmValue);
        Serial.print("[Motor] CW @ PWM=");
        Serial.println(pwmValue);
    }
    else
    {
        // Reverse direction (CCW) - speed maps 128-255 to 0-255 PWM
        int pwmValue = map(speed, 128, 255, 10, 255);
        digitalWrite(MOTOR_IN1, LOW);
        digitalWrite(MOTOR_IN2, HIGH);
        analogWrite(MOTOR_ENABLE, pwmValue);
        Serial.print("[Motor] CCW @ PWM=");
        Serial.println(pwmValue);
    }
}
