#include <M5Unified.h>

// スピーカーを鳴らしてから止め、そのあとマイクを 16 kHz で 1 秒測る。
// 同時には使わない。サンプル値は出さない。

void show(const char* text) {
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setCursor(10, 16);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(3);
  M5.Display.println(text);
}

void playSpeaker() {
  M5.Mic.end();
  bool began = M5.Speaker.begin();
  auto cfg = M5.Speaker.config();
  M5.Speaker.setVolume(200);
  Serial.printf("speaker_begin=%d\n", began ? 1 : 0);
  Serial.printf("speaker_enabled=%d\n", M5.Speaker.isEnabled() ? 1 : 0);
  Serial.printf("speaker_rate=%u\n", cfg.sample_rate);
  show("SPK");
  for (int i = 0; i < 2; i++) {
    bool played = M5.Speaker.tone(440, 500);
    Serial.printf("speaker_tone=%d\n", played ? 1 : 0);
    uint32_t start = millis();
    while (M5.Speaker.isPlaying() && millis() - start < 1200) {
      delay(10);
    }
    delay(250);
  }
  M5.Speaker.end();
  Serial.println("speaker_end");
}

void measureMic() {
  M5.Speaker.end();
  bool began = M5.Mic.begin();
  auto cfg = M5.Mic.config();
  Serial.printf("mic_begin=%d\n", began ? 1 : 0);
  Serial.printf("mic_enabled=%d\n", M5.Mic.isEnabled() ? 1 : 0);
  Serial.printf("mic_rate=%u\n", cfg.sample_rate);
  Serial.printf("mic_over=%u\n", cfg.over_sampling);
  show("MIC");

  constexpr size_t samplesPerFrame = 320;
  constexpr int framesWanted = 50;
  int16_t buffer[samplesPerFrame];
  uint32_t frames = 0;
  uint32_t peak = 0;
  uint64_t absSum = 0;
  uint32_t start = millis();
  while (frames < framesWanted) {
    if (!M5.Mic.record(buffer, samplesPerFrame, 16000)) {
      Serial.println("mic_record=fail");
      break;
    }
    for (size_t i = 0; i < samplesPerFrame; i++) {
      uint32_t magnitude = buffer[i] < 0 ? (uint32_t)(-buffer[i]) : (uint32_t)buffer[i];
      if (magnitude > peak) {
        peak = magnitude;
      }
      absSum += magnitude;
    }
    frames++;
  }
  uint32_t elapsed = millis() - start;
  uint32_t samples = frames * samplesPerFrame;
  uint32_t mean = samples ? (uint32_t)(absSum / samples) : 0;
  Serial.printf("mic_frames=%u\n", frames);
  Serial.printf("mic_elapsed_ms=%u\n", elapsed);
  Serial.printf("mic_peak=%u\n", peak);
  Serial.printf("mic_mean=%u\n", mean);
  M5.Mic.end();
  Serial.println("mic_end");
}

void setup() {
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  cfg.clear_display = true;
  cfg.output_power = false;
  cfg.internal_imu = false;
  cfg.internal_rtc = false;
  cfg.internal_mic = true;
  cfg.internal_spk = true;
  cfg.external_display_value = 0;
  cfg.led_brightness = 0;
  M5.begin(cfg);
  M5.Display.setBrightness(128);

  playSpeaker();
  delay(200);
  measureMic();
  show("DONE");
  Serial.println("audio_check=done");
}

void loop() {
}
