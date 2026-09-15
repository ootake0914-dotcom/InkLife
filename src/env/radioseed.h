#pragma once
// env/radioseed.h — 周囲のWiFi/BLE電波をエントロピー源にする。
// RSSIは揺らぐ・MAC集合は変わる→予測不能なseedになる。遺伝のRNGに使う。
// 重いスキャンはcore0ワーカーで回す想定 (ブロッキング数秒)。
// 電波を出さない (受動スキャンのみ)。失敗時はesp_randomに縮退。
#include <Arduino.h>
#include <WiFi.h>
#include <BLEDevice.h>

namespace radio {

struct Survey {
  uint32_t seed = 0;   // 合成seed (繁殖RNG用)
  uint8_t wifiN = 0;   // 検出AP数
  int8_t wifiMax = -127;  // 最強RSSI
  uint8_t bleN = 0;    // 検出BLE数
  int8_t bleMax = -127;
  bool bleOk = false;  // BLE成功否か
};

inline uint32_t fnvMix(uint32_t h, uint32_t v) { return (h ^ v) * 16777619UL; }

// allowBle=falseでBLEを飛ばす (NVSキルスイッチ用)。
inline void survey(Survey& out, bool allowBle) {
  // static再利用時の前回値残存を消去 (弱電波・BLE無効時のstale防止)。
  out.seed = 0;
  out.wifiN = 0;
  out.wifiMax = -127;
  out.bleN = 0;
  out.bleMax = -127;
  out.bleOk = false;
  uint32_t h = 2166136261UL;
  h = fnvMix(h, (uint32_t)ESP.getEfuseMac());
  h = fnvMix(h, esp_random());

  // WiFi受動スキャン
  WiFi.mode(WIFI_STA);
  int n = WiFi.scanNetworks(false, true);  // async=false, show_hidden=true
  if (n < 0) n = 0;
  if (n > 32) n = 32;  // 上限 (時間・メモリ抑制)
  out.wifiN = (uint8_t)n;
  for (int i = 0; i < n; i++) {
    int r = WiFi.RSSI(i);
    if (r > out.wifiMax) out.wifiMax = (int8_t)r;
    String bssid = WiFi.BSSIDstr(i);
    for (unsigned k = 0; k < bssid.length(); k++) h = fnvMix(h, bssid[k]);
    h = fnvMix(h, (uint32_t)(r & 0xFF));
  }
  WiFi.scanDelete();
  WiFi.mode(WIFI_OFF);  // 電波停止・節電
  h = fnvMix(h, esp_random());

  // BLE受動スキャン (2秒)。失敗しても続行。
  if (allowBle) {
    static bool bleInitDone = false;
    if (!bleInitDone) {
      BLEDevice::init("inklife");
      bleInitDone = true;
    }
    BLEScan* scan = BLEDevice::getScan();
    scan->setActiveScan(true);
    scan->setInterval(80);
    scan->setWindow(60);
    BLEScanResults* res = scan->start(2, false);
    int m = res ? res->getCount() : 0;
    if (m > 32) m = 32;
    out.bleN = (uint8_t)m;
    for (int i = 0; i < m; i++) {
      BLEAdvertisedDevice d = res->getDevice(i);
      int r = d.getRSSI();
      if (r > out.bleMax) out.bleMax = (int8_t)r;
      String a = d.getAddress().toString().c_str();
      for (unsigned k = 0; k < a.length(); k++) h = fnvMix(h, a[k]);
      h = fnvMix(h, (uint32_t)(r & 0xFF));
    }
    scan->clearResults();
    out.bleOk = true;
  }
  out.seed = h ? h : 0x9E3779B9UL;
}

}  // namespace radio
