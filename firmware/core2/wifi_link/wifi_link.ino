#include <M5Unified.h>
#include <Preferences.h>
#include <WiFi.h>
#include <string.h>
#include <WebSocketsClient.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include "secrets.h"
#include "face_frames.h"

// Wi-Fi で Gateway に hello し、マイクを 16 kHz で最大 1.6 秒送って、戻った音声を鳴らす。
// 声のあとに kTrailFrames（0.2 秒）の静けさがあれば、そこで録音を終える。
// 下りは kJitterFrames（0.2 秒）たまったところで再生を始める。全部は待たない。
// 画面下の cb / ag / gb は、0.6 秒押し続けたときだけ切り替える。それより上のタッチで止まる。
// マイクとスピーカーは同時に使わない。
// サンプル値は出さない。時刻は latency mark= だけ残す。

constexpr int kSamplesPerFrame = 320;
constexpr int kFrames = 80;
constexpr int kChatFrames = 300;
constexpr int kChatTrailFrames = 40;
constexpr uint32_t kSpeechMean = 180;
constexpr uint32_t kChatSpeechMean = 500;
constexpr int kChatStartFrames = 5;
constexpr int kChatMinHotFrames = 8;
constexpr int kTrailFrames = 10;
constexpr int kJitterFrames = 10;
constexpr int kDownlinkFrames = 2400;  // 48 秒分。PSRAM に確保する。
constexpr int kTurnLimit = 20;
constexpr int kButtonY = 204;
constexpr int kButtonH = 36;
constexpr size_t kPcmBytes = kSamplesPerFrame * sizeof(int16_t);
constexpr size_t kPacketBytes = 20 + kPcmBytes;

enum Step { STEP_WAIT, STEP_RECORD, STEP_SEND, STEP_PLAY, STEP_DONE };
enum TalkMode { MODE_CB, MODE_AG, MODE_GB };

WebSocketsClient gateway;
bool faceReady = false;
int faceFrame = -1;
uint32_t nextBlink = 3000;
uint32_t blinkUntil = 0;
int16_t* uplink = nullptr;
int16_t* downlink = nullptr;
Step step = STEP_WAIT;
bool helloSeen = false;
bool pongSeen = false;
bool muteSeen = false;
int uplinkFrames = 0;
int downlinkFrames = 0;
int badFrames = 0;
int droppedFrames = 0;
int turn = 0;
bool stopAsked = false;
uint32_t turnMark = 0;
TalkMode talkMode = MODE_AG;
bool modeDirty = true;
bool gbHolding = false;
bool listenAgain = false;
int heldButton = -1;
int heldX = 0;
int heldY = 0;
uint32_t heldSince = 0;
uint32_t modeQuietUntil = 0;
uint32_t lastButtonDown = 0;
bool buttonLatched = false;
bool replyDone = false;
Preferences prefs;

const char* modeName() {
  if (talkMode == MODE_CB) {
    return "cb";
  }
  if (talkMode == MODE_GB) {
    return "gb";
  }
  return "ag";
}

void drawButtons() {
  const char* labels[3] = {"cb", "ag", "gb"};
  int widths[3] = {106, 108, 106};
  int x = 0;
  M5.Display.setTextSize(2);
  for (int i = 0; i < 3; i++) {
    bool on = talkMode == static_cast<TalkMode>(i);
    uint16_t fill = on ? M5.Display.color565(40, 72, 52) : M5.Display.color565(232, 236, 230);
    uint16_t ink = on ? TFT_WHITE : TFT_BLACK;
    M5.Display.fillRect(x, kButtonY, widths[i], kButtonH, fill);
    M5.Display.drawRect(x, kButtonY, widths[i], kButtonH, TFT_BLACK);
    M5.Display.setTextColor(ink, fill);
    M5.Display.setCursor(x + (widths[i] - 24) / 2, kButtonY + 10);
    M5.Display.print(labels[i]);
    x += widths[i];
  }
}

void sendMode() {
  char body[48];
  snprintf(body, sizeof(body), "{\"type\":\"mode\",\"value\":\"%s\"}", modeName());
  if (!gateway.sendTXT(body)) {
    return;
  }
  modeDirty = false;
  Serial.printf("mode=%s\n", modeName());
}

int buttonIndex(int x, int y) {
  if (y < kButtonY + 16 || y >= 240 || x < 0 || x >= 320) {
    return -1;
  }
  if (x < 106) {
    return 0;
  }
  if (x < 214) {
    return 1;
  }
  return 2;
}

void applyMode(TalkMode next) {
  if (next == talkMode) {
    return;
  }
  talkMode = next;
  modeDirty = true;
  gbHolding = false;
  faceFrame = -1;
  prefs.putUChar("mode", static_cast<uint8_t>(talkMode));
  Serial.printf("mode=%s\n", modeName());
}

bool modeLocked() {
  return step == STEP_PLAY || (int32_t)(modeQuietUntil - millis()) > 0;
}

bool checkStop() {
  if (stopAsked) {
    return true;
  }
  M5.update();
  auto touch = M5.Touch.getDetail();
  if (modeLocked()) {
    heldButton = -1;
  }
  if (touch.wasPressed()) {
    Serial.printf("touch x=%d y=%d\n", touch.x, touch.y);
    int index = buttonIndex(touch.x, touch.y);
    if (index >= 0) {
      uint32_t now = millis();
      bool chatter = lastButtonDown != 0 && now - lastButtonDown < 400;
      lastButtonDown = now;
      heldButton = -1;
      if (chatter || modeLocked()) {
        buttonLatched = true;
      } else {
        heldButton = index;
        heldSince = now;
        heldX = touch.x;
        heldY = touch.y;
        buttonLatched = false;
      }
    } else if (touch.y < kButtonY) {
      heldButton = -1;
      stopAsked = true;
      Serial.println("stop=touch");
    }
  } else if (buttonLatched) {
    if (!touch.isPressed()) {
      buttonLatched = false;
    }
  } else if (heldButton >= 0 && touch.isPressed()) {
    int dx = touch.x - heldX;
    int dy = touch.y - heldY;
    if (buttonIndex(touch.x, touch.y) != heldButton || dx * dx + dy * dy > 36 * 36) {
      heldButton = -1;
    } else if (millis() - heldSince >= 600) {
      applyMode(static_cast<TalkMode>(heldButton));
      heldButton = -1;
      buttonLatched = true;
    }
  } else if (!touch.isPressed()) {
    heldButton = -1;
  }
  return stopAsked;
}

void refreshFace() {
  if (!faceReady) {
    return;
  }
  uint32_t now = millis();
  if (step != STEP_PLAY && now >= nextBlink) {
    blinkUntil = now + 140;
    nextBlink = now + 4000;
  }
  int frame = 0;
  if (step == STEP_PLAY) {
    frame = ((now / 160) & 1) ? 3 : 2;
  } else if (now < blinkUntil) {
    frame = 1;
  }
  if (frame == faceFrame) {
    return;
  }
  faceFrame = frame;
  const uint8_t* data = face_idle_jpg;
  unsigned int len = face_idle_jpg_len;
  if (frame == 1) {
    data = face_blink_jpg;
    len = face_blink_jpg_len;
  } else if (frame == 2) {
    data = face_speak_jpg;
    len = face_speak_jpg_len;
  } else if (frame == 3) {
    data = face_talk_jpg;
    len = face_talk_jpg_len;
  }
  M5.Display.drawJpg(data, len, 0, 0);
  drawButtons();
}

void show(const char* text) {
  if (!faceReady) {
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setCursor(10, 16);
    M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
    M5.Display.setTextSize(3);
    M5.Display.println(text);
    return;
  }
  refreshFace();
}

bool beginFace() {
  M5.Display.fillScreen(M5.Display.color565(213, 228, 216));
  faceReady = M5.Display.drawJpg(face_idle_jpg, face_idle_jpg_len, 0, 0);
  faceFrame = faceReady ? 0 : -1;
  if (faceReady) {
    drawButtons();
  }
  Serial.printf("face_draw=%d\n", faceReady ? 1 : 0);
  return faceReady;
}

bool contains(const uint8_t* data, size_t length, const char* needle) {
  size_t needleLength = strlen(needle);
  if (needleLength == 0 || needleLength > length) {
    return false;
  }
  for (size_t i = 0; i + needleLength <= length; i++) {
    if (memcmp(data + i, needle, needleLength) == 0) {
      return true;
    }
  }
  return false;
}

int16_t* allocSamples(int frames) {
  size_t bytes = (size_t)frames * kSamplesPerFrame * sizeof(int16_t);
  void* memory = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (memory == nullptr) {
    memory = malloc(bytes);
  }
  return static_cast<int16_t*>(memory);
}

void levels(const int16_t* data, int count, uint32_t* peak, uint32_t* mean) {
  uint32_t localPeak = 0;
  uint64_t absSum = 0;
  for (int i = 0; i < count; i++) {
    uint32_t magnitude = data[i] < 0 ? (uint32_t)(-data[i]) : (uint32_t)data[i];
    if (magnitude > localPeak) {
      localPeak = magnitude;
    }
    absSum += magnitude;
  }
  *peak = localPeak;
  *mean = count ? (uint32_t)(absSum / count) : 0;
}

void sendHello() {
  char body[480];
  snprintf(
      body,
      sizeof(body),
      "{\"type\":\"hello\",\"protocol_version\":1,\"device_id\":\"%s\",\"token\":\"%s\","
      "\"audio_in\":{\"rate\":16000,\"channels\":1,\"format\":\"pcm_s16le\"}}",
      HAGAKURE_DEVICE_ID,
      HAGAKURE_DEVICE_TOKEN);
  gateway.sendTXT(body);
  Serial.println("hello=sent");
}

void takeDownlink(const uint8_t* payload, size_t length) {
  if (payload == nullptr || length < 20 || downlink == nullptr) {
    badFrames++;
    return;
  }
  if (payload[0] != 'H' || payload[1] != 'G' || payload[2] != 1 || payload[3] != 2) {
    badFrames++;
    return;
  }
  uint16_t rate = payload[12] | (payload[13] << 8);
  uint16_t nbytes = payload[14] | (payload[15] << 8);
  if (rate != 16000 || nbytes != kPcmBytes || length != kPacketBytes) {
    badFrames++;
    return;
  }
  if (downlinkFrames >= kDownlinkFrames) {
    droppedFrames++;
    return;
  }
  if (downlinkFrames == 0) {
    Serial.printf("latency mark=downlink_first t_ms=%lu\n", millis() - turnMark);
  }
  memcpy(downlink + downlinkFrames * kSamplesPerFrame, payload + 20, kPcmBytes);
  downlinkFrames++;
}

void onGateway(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_DISCONNECTED) {
    Serial.println("ws=closed");
    helloSeen = false;
    pongSeen = false;
    muteSeen = false;
    if (step != STEP_DONE) {
      step = STEP_WAIT;
    }
    return;
  }
  if (type == WStype_CONNECTED) {
    Serial.println("ws=connected");
    show("GW");
    sendHello();
    return;
  }
  if (type == WStype_BIN) {
    takeDownlink(payload, length);
    return;
  }
  if (type != WStype_TEXT || payload == nullptr) {
    return;
  }
  if (contains(payload, length, "\"type\": \"reply_done\"")) {
    replyDone = true;
    return;
  }
  if (!helloSeen && contains(payload, length, "hello_ack")) {
    helloSeen = true;
    Serial.printf(
        "hello_ack=1 mic_enabled=%d cloud=%d\n",
        contains(payload, length, "\"mic_enabled\": false") ? 0 : 1,
        contains(payload, length, "\"cloud_active\": false") ? 0 : 1);
    gateway.sendTXT("{\"type\":\"ping\"}");
    Serial.println("ping=sent");
    return;
  }
  if (!pongSeen && contains(payload, length, "pong")) {
    pongSeen = true;
    Serial.println("pong=1");
    gateway.sendTXT("{\"type\":\"mute\",\"mic_enabled\":true}");
    Serial.println("mute=sent");
    show("TALK");
    return;
  }
  if (!muteSeen && contains(payload, length, "mute_ack")) {
    muteSeen = contains(payload, length, "\"mic_enabled\": true");
    Serial.printf("mute_ack=%d\n", muteSeen ? 1 : 0);
    if (muteSeen) {
      modeDirty = true;
    }
    return;
  }
  if (contains(payload, length, "unauthorized")) {
    Serial.println("hello=unauthorized");
    show("DENY");
  }
}

void pump(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) {
    gateway.loop();
    refreshFace();
    if (checkStop()) {
      return;
    }
    delay(10);
  }
}

void logMic(uint32_t start, bool trailed, uint32_t frameMeanMax, int hotFrames) {
  uint32_t peak = 0;
  uint32_t mean = 0;
  levels(uplink, uplinkFrames * kSamplesPerFrame, &peak, &mean);
  Serial.printf("mic_frames=%d\n", uplinkFrames);
  Serial.printf("mic_stop=%s\n", trailed ? "trail" : "max");
  Serial.printf("mic_elapsed_ms=%lu\n", millis() - start);
  Serial.printf("mic_peak=%lu\n", peak);
  Serial.printf("mic_mean=%lu\n", mean);
  Serial.printf("mic_mean_max=%lu\n", frameMeanMax);
  Serial.printf("mic_hot=%d\n", hotFrames);
  turnMark = millis();
  Serial.println("latency mark=mic_end t_ms=0");
  Serial.println("mic_end");
}

void recordChat() {
  uint32_t start = millis();
  uplinkFrames = 0;
  bool heard = false;
  int startFrames = 0;
  int quietFrames = 0;
  bool trailed = false;
  uint32_t frameMeanMax = 0;
  int hotFrames = 0;
  Serial.printf("turn=%d\n", turn + 1);
  Serial.println("mic_wait=speech");
  // M5.Mic.record が内部で参照し終えるまで生存する領域に置く。
  static int16_t frame[kSamplesPerFrame];
  while (uplinkFrames < kChatFrames) {
    if (checkStop()) {
      break;
    }
    if (talkMode != MODE_CB) {
      break;
    }
    if (!M5.Mic.record(frame, kSamplesPerFrame, 16000)) {
      Serial.println("mic_record=fail");
      break;
    }
    uint32_t framePeak = 0;
    uint32_t frameMean = 0;
    levels(frame, kSamplesPerFrame, &framePeak, &frameMean);
    if (frameMean > frameMeanMax) {
      frameMeanMax = frameMean;
    }
    if (!heard) {
      if (frameMean < kChatSpeechMean) {
        startFrames = 0;
        uplinkFrames = 0;
        gateway.loop();
        refreshFace();
        continue;
      }
      startFrames++;
    }
    memcpy(uplink + uplinkFrames * kSamplesPerFrame, frame, kPcmBytes);
    uplinkFrames++;
    if (!heard) {
      if (startFrames >= kChatStartFrames) {
        heard = true;
        hotFrames = startFrames;
      }
      gateway.loop();
      refreshFace();
      continue;
    }
    if (frameMean >= kChatSpeechMean) {
      hotFrames++;
      quietFrames = 0;
    } else {
      quietFrames++;
      if (quietFrames >= kChatTrailFrames) {
        trailed = true;
        break;
      }
    }
    gateway.loop();
    refreshFace();
  }
  if (stopAsked || talkMode != MODE_CB) {
    if (stopAsked) {
      uplinkFrames = 0;
    } else if (uplinkFrames == 0) {
      listenAgain = true;
    }
  } else if (!heard) {
    uplinkFrames = 0;
    listenAgain = true;
  } else if (hotFrames < kChatMinHotFrames) {
    uplinkFrames = 0;
    listenAgain = true;
  }
  logMic(start, trailed, frameMeanMax, hotFrames);
}

void recordMic() {
  M5.Speaker.end();
  bool began = M5.Mic.begin();
  Serial.printf("mic_begin=%d\n", began ? 1 : 0);
  Serial.printf("mic_rate=%u\n", M5.Mic.config().sample_rate);
  if (talkMode == MODE_CB) {
    recordChat();
    M5.Mic.end();
    return;
  }
  uint32_t waitMs = turn == 0 ? 2000 : 400;
  Serial.printf("turn=%d\n", turn + 1);
  Serial.printf("mic_wait_ms=%lu\n", waitMs);
  pump(waitMs);
  if (stopAsked) {
    M5.Mic.end();
    uplinkFrames = 0;
    turnMark = millis();
    Serial.println("latency mark=mic_end t_ms=0");
    Serial.println("mic_end");
    return;
  }
  uint32_t start = millis();
  uplinkFrames = 0;
  bool heard = false;
  int quietFrames = 0;
  bool trailed = false;
  uint32_t frameMeanMax = 0;
  int hotFrames = 0;
  while (uplinkFrames < kFrames) {
    if (checkStop()) {
      break;
    }
    if (!M5.Mic.record(uplink + uplinkFrames * kSamplesPerFrame, kSamplesPerFrame, 16000)) {
      Serial.println("mic_record=fail");
      break;
    }
    uint32_t framePeak = 0;
    uint32_t frameMean = 0;
    levels(uplink + uplinkFrames * kSamplesPerFrame, kSamplesPerFrame, &framePeak, &frameMean);
    uplinkFrames++;
    if (frameMean > frameMeanMax) {
      frameMeanMax = frameMean;
    }
    if (frameMean >= kSpeechMean) {
      hotFrames++;
      heard = true;
      quietFrames = 0;
    } else if (heard) {
      quietFrames++;
      if (quietFrames >= kTrailFrames) {
        trailed = true;
        break;
      }
    }
    gateway.loop();
    refreshFace();
  }
  M5.Mic.end();
  if (stopAsked) {
    uplinkFrames = 0;
  }
  logMic(start, trailed, frameMeanMax, hotFrames);
}

void packFrame(uint8_t* packet, uint32_t sequence, uint32_t timestampMs, const int16_t* pcm) {
  memset(packet, 0, kPacketBytes);
  packet[0] = 'H';
  packet[1] = 'G';
  packet[2] = 1;
  packet[3] = 1;
  packet[4] = sequence;
  packet[5] = sequence >> 8;
  packet[6] = sequence >> 16;
  packet[7] = sequence >> 24;
  packet[8] = timestampMs;
  packet[9] = timestampMs >> 8;
  packet[10] = timestampMs >> 16;
  packet[11] = timestampMs >> 24;
  packet[12] = 16000 & 0xff;
  packet[13] = (16000 >> 8) & 0xff;
  packet[14] = kPcmBytes & 0xff;
  packet[15] = (kPcmBytes >> 8) & 0xff;
  memcpy(packet + 20, pcm, kPcmBytes);
}

void sendUplink() {
  if (uplinkFrames == 0) {
    Serial.println("uplink_frames=0");
    return;
  }
  downlinkFrames = 0;
  replyDone = false;
  badFrames = 0;
  droppedFrames = 0;
  uint8_t packet[kPacketBytes];
  int sent = 0;
  for (int i = 0; i < uplinkFrames; i++) {
    packFrame(packet, i + 1, (i + 1) * 20, uplink + i * kSamplesPerFrame);
    if (!gateway.sendBIN(packet, kPacketBytes)) {
      Serial.println("uplink_send=fail");
      break;
    }
    sent++;
    gateway.loop();
    // 長い cb 発話を一度に流すと Wi-Fi タスクを飢えさせるため、毎フレーム譲る。
    delay(2);
  }
  Serial.printf("uplink_frames=%d\n", sent);
  gateway.sendTXT("{\"type\":\"utterance_end\"}");
  Serial.println("utterance_end=sent");
  Serial.printf("latency mark=uplink_sent t_ms=%lu\n", millis() - turnMark);
  receiveAndPlay();
  uint32_t peak = 0;
  uint32_t mean = 0;
  int samples = downlinkFrames * kSamplesPerFrame;
  levels(downlink, samples, &peak, &mean);
  bool matched = downlinkFrames == uplinkFrames && uplinkFrames > 0 &&
                 memcmp(uplink, downlink, samples * sizeof(int16_t)) == 0;
  Serial.printf("downlink_frames=%d\n", downlinkFrames);
  Serial.printf("downlink_bad=%d\n", badFrames);
  Serial.printf("downlink_dropped=%d\n", droppedFrames);
  Serial.printf("downlink_peak=%lu\n", peak);
  Serial.printf("downlink_mean=%lu\n", mean);
  Serial.printf("echo_match=%d\n", matched ? 1 : 0);
}

void receiveAndPlay() {
  uint32_t start = millis();
  uint32_t lastNew = start;
  uint32_t playStarted = 0;
  int seen = downlinkFrames;
  int played = 0;
  bool started = false;
  bool heardPlaying = false;
  while (true) {
    gateway.loop();
    refreshFace();
    if (checkStop()) {
      if (started) {
        M5.Speaker.stop();
      }
      break;
    }
    if (step == STEP_WAIT) {
      break;
    }
    if (downlinkFrames != seen) {
      seen = downlinkFrames;
      lastNew = millis();
    }
    bool idle = seen > 0 && millis() - lastNew > 400;
    if (!started && downlinkFrames > 0 && (downlinkFrames >= kJitterFrames || idle)) {
      M5.Mic.end();
      bool began = M5.Speaker.begin();
      M5.Speaker.setVolume(200);
      step = STEP_PLAY;
      started = true;
      playStarted = millis();
      Serial.printf("speaker_begin=%d\n", began ? 1 : 0);
      Serial.printf("speaker_rate=%u\n", M5.Speaker.config().sample_rate);
      Serial.printf(
          "latency mark=play_start t_ms=%lu buffered=%d\n",
          playStarted - turnMark,
          downlinkFrames);
      show("SPK");
    }
    if (started && downlinkFrames > played && M5.Speaker.isPlaying(0) < 2) {
      int count = downlinkFrames - played;
      bool queued = M5.Speaker.playRaw(
          downlink + played * kSamplesPerFrame,
          count * kSamplesPerFrame,
          16000,
          false,
          1,
          0,
          played == 0);
      if (queued) {
        if (played == 0) {
          Serial.println("speaker_play=1");
        }
        played = downlinkFrames;
      }
    }
    if (started && M5.Speaker.isPlaying(0) > 0) {
      heardPlaying = true;
    }
    bool playbackDone = (heardPlaying || (replyDone && played > 0)) &&
                        M5.Speaker.isPlaying(0) == 0;
    if (started && replyDone && played >= downlinkFrames && playbackDone) {
      break;
    }
    if (!started && replyDone) {
      break;
    }
    if (!started && millis() - start > 20000) {
      break;
    }
    if (started && millis() - playStarted > 60000) {
      break;
    }
    delay(10);
  }
  if (started) {
    M5.Speaker.end();
    modeQuietUntil = millis() + 2000;
    Serial.println("speaker_end");
    Serial.printf("latency mark=play_end t_ms=%lu\n", millis() - turnMark);
  }
  if (step == STEP_PLAY) {
    step = STEP_SEND;
  }
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
  prefs.begin("hagakure", false);
  uint8_t saved = prefs.getUChar("mode", MODE_AG);
  if (saved <= MODE_GB) {
    talkMode = static_cast<TalkMode>(saved);
  }
  Serial.printf("reset_reason=%d\n", static_cast<int>(esp_reset_reason()));
  M5.Mic.end();
  M5.Speaker.end();
  M5.Display.setBrightness(128);
  beginFace();
  uplink = allocSamples(kChatFrames);
  downlink = allocSamples(kDownlinkFrames);
  if (uplink == nullptr || downlink == nullptr) {
    show("MEM");
    Serial.println("audio_alloc=fail");
    return;
  }
  show("WIFI");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  int hits = 0;
  int networks = WiFi.scanNetworks();
  for (int i = 0; i < networks; i++) {
    if (WiFi.SSID(i) == HAGAKURE_WIFI_SSID) {
      hits++;
      Serial.printf("ssid_seen=1 ch=%d rssi=%d\n", WiFi.channel(i), WiFi.RSSI(i));
    }
  }
  Serial.printf("scan_count=%d ssid_hits=%d\n", networks, hits);
  WiFi.scanDelete();
  WiFi.begin(HAGAKURE_WIFI_SSID, HAGAKURE_WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(200);
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("wifi=fail status=%d\n", WiFi.status());
    show("NO WIFI");
    return;
  }
  Serial.printf(
      "wifi=ok ip=%s rssi=%d ch=%d\n",
      WiFi.localIP().toString().c_str(),
      WiFi.RSSI(),
      WiFi.channel());
  Serial.println("run=until_touch");
  Serial.printf("turn_limit=%d\n", kTurnLimit);
  Serial.printf(
      "vad speech_mean=%lu trail_frames=%d jitter_frames=%d\n",
      kSpeechMean,
      kTrailFrames,
      kJitterFrames);
  show("GW");
  gateway.begin(HAGAKURE_GATEWAY_HOST, HAGAKURE_GATEWAY_PORT, "/device");
  gateway.onEvent(onGateway);
  gateway.setReconnectInterval(5000);
}

void loop() {
  refreshFace();
  if (uplink == nullptr || WiFi.status() != WL_CONNECTED) {
    return;
  }
  gateway.loop();
  if (modeDirty && muteSeen) {
    sendMode();
  }
  checkStop();
  if (step == STEP_WAIT) {
    if (muteSeen) {
      step = STEP_RECORD;
    }
    return;
  }
  if (step == STEP_RECORD) {
    if (talkMode == MODE_GB) {
      if (stopAsked) {
        show("STOP");
        Serial.println("audio_roundtrip=done");
        step = STEP_DONE;
        return;
      }
      if (!gbHolding) {
        Serial.println("grok=unimplemented");
        gbHolding = true;
      }
      return;
    }
    gbHolding = false;
    listenAgain = false;
    recordMic();
    if (listenAgain) {
      return;
    }
    if (stopAsked || uplinkFrames == 0) {
      show("STOP");
      Serial.println("audio_roundtrip=done");
      step = STEP_DONE;
      return;
    }
    show("SEND");
    step = STEP_SEND;
    return;
  }
  if (step == STEP_SEND) {
    sendUplink();
    if (stopAsked) {
      show("STOP");
      Serial.println("audio_roundtrip=done");
      step = STEP_DONE;
      return;
    }
    if (step == STEP_WAIT) {
      return;
    }
    if (downlinkFrames == 0) {
      Serial.println("speaker_play=0");
      finishTurn();
      return;
    }
    finishTurn();
  }
}

void finishTurn() {
  turn++;
  Serial.printf("turn_done=%d\n", turn);
  if (stopAsked || (talkMode != MODE_CB && turn >= kTurnLimit)) {
    if (!stopAsked) {
      Serial.println("stop=limit");
    }
    step = STEP_DONE;
    show(stopAsked ? "STOP" : "DONE");
    Serial.println("audio_roundtrip=done");
    return;
  }
  step = STEP_RECORD;
  show("TALK");
}
