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
// 壁時計 (JST換算)。unix==0は未同期 (呼出側は体内時計にフォールバックすること)。
// 21-6時を夜、5-8時を朝 (おはようボーナス帯) とする。
inline uint8_t wallHourJST(uint32_t unix) {
  return (uint8_t)(((unix + 9 * 3600UL) % 86400UL) / 3600UL);
}
inline bool wallNightJST(uint32_t unix) {
  uint8_t h = wallHourJST(unix);
  return h >= 21 || h < 6;
}
inline bool wallMorningJST(uint32_t unix) {
  uint8_t h = wallHourJST(unix);
  return h >= 5 && h < 8;
}
inline uint32_t wallDayJST(uint32_t unix) { return (unix + 9 * 3600UL) / 86400UL; }
// unix秒→(月,日) JST。うるう年対応の整数演算 (Hinnant days_to_civil)。
inline void wallMonthDayJST(uint32_t unix, uint8_t& month, uint8_t& day) {
  int32_t z = (int32_t)(((unix + 9 * 3600UL) / 86400UL) + 719468);
  int32_t era = (z >= 0 ? z : z - 146096) / 146097;
  uint32_t doe = (uint32_t)(z - era * 146097);
  uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  uint32_t mp = (5 * doy + 2) / 153;
  day = (uint8_t)(doy - (153 * mp + 2) / 5 + 1);
  month = (uint8_t)(mp < 10 ? mp + 3 : mp - 9);
}
// ハロウィン期間 (10/31〜11/1)。季節帽子の表示条件。壁時計必須。
inline bool wallHalloweenJST(uint32_t unix) {
  uint8_t m = 0, d = 0;
  wallMonthDayJST(unix, m, d);
  return (m == 10 && d == 31) || (m == 11 && d == 1);
}
// サンタ期間 (12/24〜12/26)・鏡餅期間 (1/1〜1/3)。
inline bool wallSantaJST(uint32_t unix) {
  uint8_t m = 0, d = 0;
  wallMonthDayJST(unix, m, d);
  return m == 12 && d >= 24 && d <= 26;
}
inline bool wallMochiJST(uint32_t unix) {
  uint8_t m = 0, d = 0;
  wallMonthDayJST(unix, m, d);
  return m == 1 && d >= 1 && d <= 3;
}
// 季節帽子の種類: 0=なし 1=かぼちゃ 2=サンタ 3=鏡餅 (期間は重ならないが優先順つき)。
inline uint8_t hatKindJST(uint32_t unix) {
  if (wallHalloweenJST(unix)) return 1;
  if (wallSantaJST(unix)) return 2;
  if (wallMochiJST(unix)) return 3;
  return 0;
}
}  // namespace clk
