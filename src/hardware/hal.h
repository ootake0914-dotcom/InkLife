#pragma once
// hardware/hal.h — E290実機で検証済みの値のみ。推測のGPIOは置かない。
// 検証履歴: GxEPD2表示・RadioLib送受信・ボタン・LEDすべてCOM24実機で確認済み。
#include <Arduino.h>

// ---- E-Ink (DEPG0290BNS800, GxEPD2_290_BSで駆動確認) ----
#define HAL_EPD_CS   3
#define HAL_EPD_DC   4
#define HAL_EPD_RST  5
#define HAL_EPD_BUSY 6
#define HAL_EPD_SCK  2   // HSPI側
#define HAL_EPD_MOSI 1   // HSPI側

// ---- LoRa SX1262 (RadioLibで送受信確認。M5以降で使用) ----
#define HAL_LORA_NSS  8
#define HAL_LORA_DIO1 14
#define HAL_LORA_RST  12
#define HAL_LORA_BUSY 13
#define HAL_LORA_SCK  9   // FSPI側 (表示と別ペリフェラル)
#define HAL_LORA_MISO 11
#define HAL_LORA_MOSI 10

// ---- 電源・UI ----
#define HAL_VEXT   18  // HIGHで周辺給電 (表示・LoRa系)
#define HAL_LED    45  // 初期ロットに無い個体あり
#define HAL_BTN_BOOT 0
#define HAL_BTN_SIDE 21

// 周辺給電ON。表示・LoRaより先に呼ぶ (安定化待ち込み)。
inline void halPowerOn() {
  pinMode(HAL_VEXT, OUTPUT);
  digitalWrite(HAL_VEXT, HIGH);
  delay(150);  // DC-DCとパネル電源の立ち上がりを待つ
}

// ---- LED言語 (単色PWM)。心拍=生存 / 呼吸=睡眠 / 点灯=無線・操作 / 乱れ=病気 ----
namespace led {
enum Mode : uint8_t { OFF, HEART, BLIP };
static Mode cur = HEART, back = HEART;
static unsigned long t0 = 0;
static uint32_t lrng = 0x12345678u;  // LED用xorshift (HexaMIDI式: hot pathでesp_randomを呼ばない)
inline void init() {
  ledcAttach(HAL_LED, 5000, 8);
  ledcWrite(HAL_LED, 0);
  uint32_t s = esp_random();
  lrng = s ? s : 0xA53A5A35u;
  cur = HEART; t0 = millis();
}
inline void blip() { if (cur != BLIP) back = cur; cur = BLIP; t0 = millis(); }
inline void off() { cur = OFF; ledcWrite(HAL_LED, 0); }
// 50ms周期で呼ぶ。energy=元気、sleeping=睡眠中、sick=病気。
inline void tick(uint8_t energy, bool sleeping, bool sick) {
  if (cur == OFF) return;
  unsigned long t = millis() - t0;
  if (cur == BLIP) {
    if (t > 180) { cur = back; t0 = millis(); ledcWrite(HAL_LED, 0); }
    else ledcWrite(HAL_LED, 255);
    return;
  }
  if (sleeping) {  // 4秒周期の呼吸
    unsigned long ph = t % 4000;
    ledcWrite(HAL_LED, ph < 2000 ? (uint8_t)(ph * 120 / 2000) : (uint8_t)(120 - (ph - 2000) * 120 / 2000));
    return;
  }
  if (sick) {  // 不規則フリッカー (20Hz hot pathはxorshift)
    lrng ^= lrng << 13; lrng ^= lrng >> 17; lrng ^= lrng << 5;
    ledcWrite(HAL_LED, (lrng % 100 < 30) ? 200 : 0);
    return;
  }
  // 心拍 (ドクンッドクン)。元気=ゆっくり、弱り=速い
  unsigned long period = 1200 + (unsigned long)energy * 10;
  unsigned long ph = t % period;
  ledcWrite(HAL_LED, ph < 90 ? 255 : (ph >= 180 && ph < 270 ? 160 : 0));
}
}  // namespace led

inline void halInit() {
  led::init();
  pinMode(HAL_BTN_BOOT, INPUT_PULLUP);
  pinMode(HAL_BTN_SIDE, INPUT_PULLUP);
  halPowerOn();
}

// 現在のボタン生レベルbitmask (bit0=BOOT, bit1=SIDE)。長押し検出用。
inline uint8_t halLevel() {
  uint8_t r = 0;
  if (digitalRead(HAL_BTN_BOOT) == LOW) r |= 1;
  if (digitalRead(HAL_BTN_SIDE) == LOW) r |= 2;
  return r;
}

// 立ち下がりエッジ検出 (チャタリング20ms)。戻り値は押されたボタンbitmask。
inline uint8_t halButtons() {
  static int last0 = HIGH, last1 = HIGH;
  static unsigned long t0 = 0, t1 = 0;
  uint8_t r = 0;
  unsigned long now = millis();
  int b0 = digitalRead(HAL_BTN_BOOT), b1 = digitalRead(HAL_BTN_SIDE);
  if (b0 == LOW && last0 == HIGH && now - t0 > 20) { r |= 1; t0 = now; }
  if (b1 == LOW && last1 == HIGH && now - t1 > 20) { r |= 2; t1 = now; }
  last0 = b0; last1 = b1;
  return r;
}
