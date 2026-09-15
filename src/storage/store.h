#pragma once
// storage/store.h — NVS永続化。電源断・flash後も個体を復元する。
// フラッシュ消耗を抑えるため保存は呼び出し側が間引く (例: 4周回に1回)。
// RTCメモリ(高速・揮発)と併用し、NVSは電源断時の保険。
#include <Arduino.h>
#include <Preferences.h>
#include "../life/creature.h"

namespace store {

static const char* NS = "inklife";
static const uint32_t MAGIC = 0x494E4C34;  // "INK4"
static const uint8_t VER = 2;  // v2: habit[3]追加。v1読込互換あり (飽き0扱い)

// NVSへ保存。戻り値=falseは書込失敗。pev=未送EVENT (再起動越え用)。
inline bool save(const Creature& c, const char* event, uint64_t rtc_us, uint32_t unix, uint8_t pendingEvt) {
  Preferences p;
  if (!p.begin(NS, false)) return false;
  p.putULong("magic", MAGIC);
  p.putUChar("ver", VER);
  p.putULong("did", c.device_id);
  p.putUShort("species", c.species_id);
  p.putUChar("gen", c.generation);
  p.putUChar("hp", c.health);
  p.putUChar("hu", c.hunger);
  p.putUChar("en", c.energy);
  p.putUChar("ha", c.happiness);
  p.putUChar("cl", c.cleanliness);
  p.putUChar("in", c.intelligence);
  p.putUChar("cu", c.curiosity);
  p.putUChar("ag", c.aggression);
  p.putUChar("so", c.sociability);
  p.putULong("age", c.age_sec);
  p.putUChar("act", (uint8_t)c.action);
  p.putUChar("slp", c.sleeping ? 1 : 0);
  p.putULong64("rrtc", rtc_us);
  p.putULong("runix", unix);
  p.putString("ev", event);
  p.putUChar("pev", pendingEvt);
  p.putBytes("fuse", c.fuse, 4);
  p.putUChar("hb0", c.habit[0]);
  p.putUChar("hb1", c.habit[1]);
  p.putUChar("hb2", c.habit[2]);
  p.end();
  return true;
}

// NVSから復元。戻り値false=データ無し/世代不一致 (新規個体にすること)。
// pev無し旧データは0扱い (後方互換)。v1はhabit無し→0扱い。
inline bool load(Creature& c, char* event, size_t evlen, uint64_t& rrtc, uint32_t& runix, uint8_t& pev) {
  Preferences p;
  if (!p.begin(NS, true)) return false;
  uint8_t v = p.getUChar("ver", 0);
  bool ok = p.getULong("magic", 0) == MAGIC && (v == 1 || v == VER);
  if (ok) {
    uint32_t did = (uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFF);
    ok = p.getULong("did", 0) == did;  // 別チップのデータは使わない
  }
  if (!ok) { p.end(); return false; }
  c.device_id = p.getULong("did", 0);
  c.species_id = p.getUShort("species", 0);
  c.generation = p.getUChar("gen", 1);
  c.health = p.getUChar("hp", 90);
  c.hunger = p.getUChar("hu", 20);
  c.energy = p.getUChar("en", 90);
  c.happiness = p.getUChar("ha", 70);
  c.cleanliness = p.getUChar("cl", 80);
  c.intelligence = p.getUChar("in", 40);
  c.curiosity = p.getUChar("cu", 40);
  c.aggression = p.getUChar("ag", 20);
  c.sociability = p.getUChar("so", 40);
  strncpy(c.name, "INK", sizeof(c.name));
  c.age_sec = p.getULong("age", 0);
  // NVS破損時の不正Action固着を防止 (BREEDを超えたらIDLE)。
  uint8_t actv = p.getUChar("act", 0);
  c.action = (actv <= (uint8_t)Action::BREED) ? (Action)actv : Action::IDLE;
  c.sleeping = p.getUChar("slp", 0) != 0;
  rrtc = p.getULong64("rrtc", 0);
  runix = p.getULong("runix", 0);
  pev = p.getUChar("pev", 0);
  if (p.getBytes("fuse", c.fuse, 4) != 4)
    for (int i = 0; i < 4; i++) c.fuse[i] = 255;  // 旧データは純血扱い
  if (v >= 2) {
    c.habit[0] = p.getUChar("hb0", 0);
    c.habit[1] = p.getUChar("hb1", 0);
    c.habit[2] = p.getUChar("hb2", 0);
  } else {
    for (int i = 0; i < 3; i++) c.habit[i] = 0;  // v1データは飽きなし扱い
  }
  p.getString("ev", event, evlen);  // 直接バッファ読み (String不使用)
  event[evlen - 1] = 0;
  p.end();
  return true;
}

}  // namespace store
