#include <M5Unified.h>

// LCD とタッチだけ。マイク、スピーカー、Wi-Fi は使わない。

const char* powerName(m5::Power_Class::pmic_t type) {
  switch (type) {
    case m5::Power_Class::pmic_unknown: return "unknown";
    case m5::Power_Class::pmic_adc: return "adc";
    case m5::Power_Class::pmic_axp192: return "axp192";
    case m5::Power_Class::pmic_ip5306: return "ip5306";
    case m5::Power_Class::pmic_axp2101: return "axp2101";
    case m5::Power_Class::pmic_aw32001: return "aw32001";
    case m5::Power_Class::pmic_m5pm1: return "m5pm1";
  }
  return "unset";
}

void setup() {
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  cfg.clear_display = true;
  cfg.output_power = false;
  cfg.internal_imu = false;
  cfg.internal_rtc = false;
  cfg.internal_mic = false;
  cfg.internal_spk = false;
  cfg.external_display_value = 0;
  cfg.led_brightness = 0;
  M5.begin(cfg);

  const char* board = "other";
  if (M5.getBoard() == m5::board_t::board_M5StackCore2) {
    board = "M5StackCore2";
  } else if (M5.getBoard() == m5::board_t::board_unknown) {
    board = "unknown";
  }

  M5.Display.setBrightness(128);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(3);
  M5.Display.setCursor(10, 16);
  M5.Display.println("Core2");
  M5.Display.println("LCD");

  Serial.printf("board=%d %s\n", static_cast<int>(M5.getBoard()), board);
  Serial.printf("power=%s\n", powerName(M5.Power.getType()));
  Serial.printf("vbat_mV=%d\n", M5.Power.getBatteryVoltage());
  Serial.printf("display=%dx%d\n", M5.Display.width(), M5.Display.height());
  Serial.println("ready");
}

void loop() {
  M5.update();
  static bool once = false;
  if (!once) {
    Serial.println("loop");
    once = true;
  }
  auto touch = M5.Touch.getDetail();
  if (touch.wasPressed()) {
    Serial.printf("touch x=%d y=%d\n", touch.x, touch.y);
    M5.Display.fillRect(0, 100, 320, 40, TFT_BLACK);
    M5.Display.setCursor(10, 108);
    M5.Display.printf("%d,%d", touch.x, touch.y);
  }
  delay(10);
}
