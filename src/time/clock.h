#pragma once
// time/clock.h — 経過時間源。deep sleepをまたげるRTC基準。
// M2のmillis基準から昇格。時刻合わせ(NTP等)はしない (電源OFF時はM4のNVSで補完)。
// life層は秒数だけ受け取るので時刻源の変更に影響されない。
#include <Arduino.h>
// esp_rtc_get_time_usはROM/IDF由来。公開ヘッダの場所が変わりやすいため
// extern宣言で直接束縛する (未リンク時はビルドエラーで検出できる)。
extern "C" uint64_t esp_rtc_get_time_us(void);

namespace clk {
// 単調増加するRTCマイクロ秒。deep sleep中も進む (電源断でリセット)。
inline uint64_t rtcUs() { return esp_rtc_get_time_us(); }
// 2点間の経過秒 (逆行時は0)
inline uint32_t sleptSec(uint64_t prev_us, uint64_t now_us) {
  return now_us > prev_us ? (uint32_t)((now_us - prev_us) / 1000000ULL) : 0;
}
inline uint32_t now() { return millis() / 1000; }
inline uint32_t elapsed(uint32_t from, uint32_t to) {
  return to >= from ? to - from : 0;
}
}  // namespace clk
