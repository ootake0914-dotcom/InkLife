#pragma once
// radio/mesh.h — Ink Life Phase1無線 (HELLO + STATUS)。
// 低電力のため常時受信しない。送信→短受信窓→sleepの往復のみ (4周回に1回想定)。
// RSSIは近接度推定。正距測定には使わない。PhY CRCはRadioLib任せ。
#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include "../hardware/hal.h"
#include "../life/creature.h"

namespace mesh {

static const uint8_t VER = 3;  // P0: STATUSにfuse4B追加(25B)。v1/v2受信も継続対応
static const uint8_t T_HELLO = 1;
static const uint8_t T_STATUS = 2;
// M7 interaction (Phase 2)。全て `INKL|ver|type|did4` + 末尾。
static const uint8_t T_GREETING = 3;  // +phash2 (12B)。挨拶。受信→幸福+、GREETING返信
static const uint8_t T_FOOD = 4;      // +amount1 (11B)。餌おすそわけ。受信→空腹-、お礼なし
static const uint8_t T_PLAY = 5;      // 10B。遊びの誘い。受信→元気なら幸福+、PLAY返信
static const uint8_t T_FIGHT = 6;     // +power1 (11B)。勝負。受信→aggression+乱数で勝敗
static const uint8_t T_TRADE = 7;     // +give1+want1 (12B)。食料交換提案。余裕があれば受諾
static const uint8_t T_EVENT = 8;     // +code1 (11B)。誕生=1/進化=2/びょうき=3/おやすみ=4
static const float FREQ_MHZ = 923.0;  // 日本920MHz帯。法令遵守は運用者責任

SX1262 radio = new Module(HAL_LORA_NSS, HAL_LORA_DIO1, HAL_LORA_RST, HAL_LORA_BUSY);
volatile bool rxFlag = false;
void IRAM_ATTR onDio() { rxFlag = true; }

// 性格ハッシュ (FNV-1a上位16bit)。同FWでも個体識別できる名刺代わり。
inline uint16_t personHash(const Creature& c) {
  uint32_t h = 2166136261UL;
  h = (h ^ c.species_id) * 16777619UL;
  h = (h ^ c.intelligence) * 16777619UL;
  h = (h ^ c.curiosity) * 16777619UL;
  h = (h ^ c.aggression) * 16777619UL;
  h = (h ^ c.sociability) * 16777619UL;
  return (uint16_t)(h ^ (h >> 16));
}

inline bool begin() {
  ConfigLoRa_t c;
  c.frequency = FREQ_MHZ;
  c.bandwidth = 125.0;
  c.spreadingFactor = 7;
  c.codingRate = 5;
  c.syncWord = RADIOLIB_LORA_SYNC_WORD_PRIVATE;
  c.power = 10;  // 低出力。923MHz帯20mW以下を厳守
  c.preambleLength = 8;
  int st = radio.begin(c);
  if (st != RADIOLIB_ERR_NONE) return false;
  radio.setDio2AsRfSwitch(true);  // Heltec基板のRFスイッチ制御
  radio.setDio1Action(onDio);
  return true;
}

inline void sleep() { radio.sleep(); }

// HELLO 19B: INKL|ver|type|did4|species2|gen|age4|phash2 (LE)
inline bool sendHello(const Creature& c) {
  uint8_t b[19];
  b[0] = 'I'; b[1] = 'N'; b[2] = 'K'; b[3] = 'L';
  b[4] = VER; b[5] = T_HELLO;
  b[6] = c.device_id & 0xFF; b[7] = (c.device_id >> 8) & 0xFF;
  b[8] = (c.device_id >> 16) & 0xFF; b[9] = (c.device_id >> 24) & 0xFF;
  b[10] = c.species_id & 0xFF; b[11] = (c.species_id >> 8) & 0xFF;
  b[12] = c.generation;
  b[13] = c.age_sec & 0xFF; b[14] = (c.age_sec >> 8) & 0xFF;
  b[15] = (c.age_sec >> 16) & 0xFF; b[16] = (c.age_sec >> 24) & 0xFF;
  uint16_t ph = personHash(c);
  b[17] = ph & 0xFF; b[18] = (ph >> 8) & 0xFF;
  return radio.transmit(b, sizeof(b)) == RADIOLIB_ERR_NONE;
}

// STATUS 25B(v3): INKL|ver|type|did4|hp,hu,en,ha,cl|act|mood|in,cu,ag,so|fz4
// v1(17B, 形質なし)・v2(21B, fuseなし)も受信する。fuseは255=空きのまま送る。
inline bool sendStatus(const Creature& c) {
  uint8_t b[25];
  b[0] = 'I'; b[1] = 'N'; b[2] = 'K'; b[3] = 'L';
  b[4] = VER; b[5] = T_STATUS;
  b[6] = c.device_id & 0xFF; b[7] = (c.device_id >> 8) & 0xFF;
  b[8] = (c.device_id >> 16) & 0xFF; b[9] = (c.device_id >> 24) & 0xFF;
  b[10] = c.health; b[11] = c.hunger; b[12] = c.energy;
  b[13] = c.happiness; b[14] = c.cleanliness;
  b[15] = (uint8_t)c.action;
  b[16] = (uint8_t)creatureMood(c);
  b[17] = c.intelligence; b[18] = c.curiosity;
  b[19] = c.aggression; b[20] = c.sociability;
  b[21] = c.fuse[0]; b[22] = c.fuse[1];
  b[23] = c.fuse[2]; b[24] = c.fuse[3];
  return radio.transmit(b, sizeof(b)) == RADIOLIB_ERR_NONE;
}

// interaction送信ヘルパ。buf末尾のみ型ごとに詰める。
inline bool sendRaw(uint8_t type, uint32_t did, const uint8_t* tail, uint8_t tlen) {
  if (tlen > 2) return false;  // 12Bパケット上限 (範囲外読出防止)
  uint8_t b[12];
  b[0] = 'I'; b[1] = 'N'; b[2] = 'K'; b[3] = 'L';
  b[4] = VER; b[5] = type;
  b[6] = did & 0xFF; b[7] = (did >> 8) & 0xFF;
  b[8] = (did >> 16) & 0xFF; b[9] = (did >> 24) & 0xFF;
  for (uint8_t i = 0; i < tlen && 10 + i < (uint8_t)sizeof(b); i++) b[10 + i] = tail[i];
  return radio.transmit(b, 10 + tlen) == RADIOLIB_ERR_NONE;
}
inline bool sendGreeting(const Creature& c) {
  uint16_t ph = personHash(c);
  uint8_t t[2] = {(uint8_t)(ph & 0xFF), (uint8_t)(ph >> 8)};
  return sendRaw(T_GREETING, c.device_id, t, 2);
}
inline bool sendFood(const Creature& c, uint8_t amount) {
  return sendRaw(T_FOOD, c.device_id, &amount, 1);
}
inline bool sendPlay(const Creature& c) { return sendRaw(T_PLAY, c.device_id, nullptr, 0); }
inline bool sendFight(const Creature& c) {
  uint8_t p = c.aggression;
  return sendRaw(T_FIGHT, c.device_id, &p, 1);
}
inline bool sendTrade(const Creature& c, uint8_t give, uint8_t want) {
  uint8_t t[2] = {give, want};
  return sendRaw(T_TRADE, c.device_id, t, 2);
}
inline bool sendEvent(const Creature& c, uint8_t code) {
  return sendRaw(T_EVENT, c.device_id, &code, 1);
}
struct Peer {
  bool valid = false;
  uint8_t type = 0;
  uint32_t did = 0;
  uint16_t species = 0;
  uint8_t gen = 0;
  uint32_t age = 0;
  uint16_t phash = 0;
  uint8_t hp = 0, hu = 0, en = 0, ha = 0, cl = 0, act = 0, mood = 0;
  uint8_t ti = 0, cu = 0, ag = 0, so = 0;  // v2形質。hasTrで有無判定
  bool hasTr = false;
  uint8_t fz[4] = {255, 255, 255, 255};  // v3融合遺伝子。hasFzで有無判定
  bool hasFz = false;
  uint8_t x1 = 0, x2 = 0;  // interaction末尾 (意味はtype依存)
  float rssi = 0;
  float snr = 0;
};

// パケット解析コア。無線受信とシリアルINJECT疑似試験で共用 (同一バイナリ判定)。
// 戻り値true=妥当なINKLパケット。out.validも立てる。
inline bool parsePacket(const uint8_t* b, int n, float rssi, float snr, Peer& out) {
  out = Peer();  // 再利用時の前回値残存を消去 (v1 STATUSのhasTr等)
  out.valid = false;
  if (n < 7) return false;
  if (b[0] != 'I' || b[1] != 'N' || b[2] != 'K' || b[3] != 'L') return false;
  if (b[4] < 1 || b[4] > VER) return false;  // v1/v2/v3を受理 (VER上げ時の取りこぼし防止)
  uint8_t t = b[5];
  if (t < T_HELLO || t > T_EVENT) return false;  // 未知typeは破棄 (知人帳のゴミ枠消費防止)
  if (t == T_HELLO && n < 19) return false;
  if (t == T_STATUS && n < 17) return false;
  if (t >= T_GREETING && t <= T_EVENT && n < 10) return false;  // PLAY最小10B
  out.valid = true;
  out.type = t;
  out.did = (uint32_t)b[6] | ((uint32_t)b[7] << 8) |
            ((uint32_t)b[8] << 16) | ((uint32_t)b[9] << 24);
  if (out.type == T_HELLO && n >= 19) {
    out.species = b[10] | ((uint16_t)b[11] << 8);
    out.gen = b[12];
    out.age = (uint32_t)b[13] | ((uint32_t)b[14] << 8) |
              ((uint32_t)b[15] << 16) | ((uint32_t)b[16] << 24);
    out.phash = b[17] | ((uint16_t)b[18] << 8);
  } else if (out.type == T_STATUS && n >= 17) {
    out.hp = b[10]; out.hu = b[11]; out.en = b[12];
    out.ha = b[13]; out.cl = b[14];
    out.act = b[15]; out.mood = b[16];
    if (n >= 21) {
      out.ti = b[17]; out.cu = b[18]; out.ag = b[19]; out.so = b[20];
      out.hasTr = true;
    }
    if (n >= 25) {  // v3融合遺伝子 (0-11実値 / 255空き。それ以外はbreed側で無視)
      out.fz[0] = b[21]; out.fz[1] = b[22];
      out.fz[2] = b[23]; out.fz[3] = b[24];
      out.hasFz = true;
    }
  } else if (out.type >= T_GREETING && out.type <= T_EVENT) {
    if (n >= 11) out.x1 = b[10];  // GREETING phash低位 / FOOD量 / FIGHT強さ / TRADE譲渡 / EVENT符号
    if (n >= 12) out.x2 = b[11];  // GREETING phash高位 / TRADE希望
  }
  out.rssi = rssi;
  out.snr = snr;
  return true;
}

// 受信窓ms。妥当なINKLパケットを受信したらtrue (自機の電波は拾わない。半二重のため)。
// pressed!=nullptr時は5ms毎にボタンを覗き、押下で受信を切り上げfalse＋格納 (ボタン即応用)。
inline bool recvWindow(Peer& out, uint32_t ms, uint8_t* pressed = nullptr) {
  out.valid = false;
  rxFlag = false;
  if (radio.startReceive() != RADIOLIB_ERR_NONE) return false;
  unsigned long t0 = millis();
  while (millis() - t0 < ms) {
    if (rxFlag) {
      rxFlag = false;
      uint8_t b[32];
      int n = radio.getPacketLength();
      if (n <= 0 || n > (int)sizeof(b)) { radio.startReceive(); continue; }
      int st = radio.readData(b, n);
      float rssi = radio.getRSSI(), snr = radio.getSNR();
      if (st == RADIOLIB_ERR_NONE && parsePacket(b, n, rssi, snr, out)) return true;
      radio.startReceive();
    }
    if (pressed) {
      // loop/pollTimeと同一のUSB列挙ノイズガード (起動直後の誤abort防止)
      if (millis() > 8000) {
        uint8_t pb = halButtons();
        if (pb) { *pressed = pb; return false; }
      }
    }
    delay(5);
  }
  return false;
}

}  // namespace mesh
