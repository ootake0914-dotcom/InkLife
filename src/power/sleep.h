#pragma once
// power/sleep.h — deep sleep周回の出入口。
// 基本形: WAKE→(inoで更新)→sleepCycle(秒)。起床要因で振る舞いを変える。
// BOOTボタン(EXT0)でも起きる。SIDEは起動中の短窓でのみ有効 (M3の割切り)。
#include <Arduino.h>
#include "esp_sleep.h"
#include "../hardware/hal.h"

namespace power {

// 今回の起動がdeep sleepからの復帰か (電源ON/リセット直後はfalse)
inline bool wokeFromSleep() {
  esp_sleep_wakeup_cause_t c = esp_sleep_get_wakeup_cause();
  return c == ESP_SLEEP_WAKEUP_TIMER || c == ESP_SLEEP_WAKEUP_EXT0;
}

inline const char* wakeName() {
  switch (esp_sleep_get_wakeup_cause()) {
    case ESP_SLEEP_WAKEUP_TIMER: return "timer";
    case ESP_SLEEP_WAKEUP_EXT0: return "button";
    default: return "poweron";
  }
}

// sec秒後にタイマ起床＋BOOTボタン起床を武装して眠る。戻らない。
inline void sleepCycle(uint32_t sec) {
  led::off();
  Serial.print("+SLEEP sec=");
  Serial.println(sec);
  Serial.flush();
  delay(50);  // USBへの吐き出し待ち

  // BOOTボタンが押されたままだとEXT0(LOW)で即座に再起動ループに陥るため、解放を待機。
  // 固着時は5秒で打ち切り、EXT0起床を武装しない (タイマ起床のみ。即時起床ループ回避)
  bool bootHeld = false;
  for (unsigned long w = millis(); digitalRead(HAL_BTN_BOOT) == LOW;) {
    if (millis() - w > 5000) { bootHeld = true; break; }
    delay(10);
  }
  delay(20);  // チャタリング安定待ち

  esp_sleep_enable_timer_wakeup((uint64_t)sec * 1000000ULL);
  if (!bootHeld)
    esp_sleep_enable_ext0_wakeup((gpio_num_t)HAL_BTN_BOOT, 0);  // BOOT押下で起床
  esp_deep_sleep_start();
}

}  // namespace power
