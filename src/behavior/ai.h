#pragma once
// behavior/ai.h — Utility AI。行動ごと効用0-100を付け最大を選ぶ。
// if文の塊にしない: スコア関数テーブル＋切替ヒステリシス (+10差で切替)。
// 新行動の追加は Entry 1行 (M7のFIGHT等はここに足す)。
#include "../life/creature.h"

namespace ai {

typedef uint8_t (*Scorer)(const Creature&, bool night, bool morning);

inline uint8_t sSleep(const Creature& c, bool night, bool) {
  uint8_t s = c.energy < 25 ? 90 : c.energy < 50 ? 55 : (c.energy > 80 ? 5 : 10);
  if (c.action == Action::SLEEP) s = min(100, (int)s + 20);  // 睡眠継続バイアス
  if (night) s = min(100, (int)s + 20);  // 夜は眠い (壁時計優先。未同期時は体内時計を呼出側が渡す)
  return s;
}
inline uint8_t sEat(const Creature& c, bool, bool morning) {
  // M2は餌無限のデモ。M7でFOOD在庫と連動させる。
  uint8_t s = c.hunger > 75 ? 85 : c.hunger > 50 ? 55 : 10;
  if (morning) s = min(100, (int)s + 20);  // 朝はお腹空いて起きる
  return s;
}
inline uint8_t sPlay(const Creature& c, bool night, bool) {
  if (c.energy < 30) return 5;
  int s = c.happiness < 40 ? 60 : 20;
  if (night) s -= 10;  // 夜更かし抑制
  if (s < 0) s = 0;
  return (uint8_t)s;
}
inline uint8_t sExplore(const Creature& c, bool night, bool) {
  if (c.energy < 50) return 5;
  int s = 20 + c.curiosity / 3;  // 好奇心が探検率になる
  if (night) s -= 10;  // 夜の探検は控えめ
  else s += 10;  // 昼は活発
  if (s < 0) s = 0;
  if (s > 100) s = 100;
  return (uint8_t)s;
}
inline uint8_t sComm(const Creature& c, bool, bool) {
  // M6で他個体が居る時だけ高くする。今は顔見知りゼロなので低空飛行。
  return c.sociability / 4;
}
inline uint8_t sSeek(const Creature&, bool, bool) { return 0; }   // M7予約
inline uint8_t sFlee(const Creature&, bool, bool) { return 0; }   // M7予約
inline uint8_t sApproach(const Creature&, bool, bool) { return 0; }  // M7予約
inline uint8_t sFight(const Creature& c, bool, bool) {
  // 知人の有無はdecide()側で見る (peers==0なら0に潰す)。
  if (c.aggression > 60 && c.health > 70) return 45;
  return 0;
}
inline uint8_t sBreed(const Creature&, bool, bool) { return 0; }  // M8予約

struct Entry { Action a; Scorer fn; };
static const Entry TABLE[] = {
  {Action::SLEEP, sSleep}, {Action::EAT, sEat}, {Action::PLAY, sPlay},
  {Action::EXPLORE, sExplore}, {Action::COMM, sComm}, {Action::SEEK, sSeek},
  {Action::FLEE, sFlee}, {Action::APPROACH, sApproach},
  {Action::FIGHT, sFight}, {Action::BREED, sBreed},
};

inline Action decide(const Creature& c, uint8_t peers = 0, bool night = false, bool morning = false) {
  Action best = Action::IDLE;
  uint8_t bestScore = 30;  // IDLEの基礎点。何もなければのんびり
  uint8_t curScore = 0;
  for (unsigned i = 0; i < sizeof(TABLE) / sizeof(TABLE[0]); i++) {
    uint8_t s = TABLE[i].fn(c, night, morning);
    // 知人が居るとCOMMが現実味を帯びる (M6)。居なければ低空飛行のまま。
    if (TABLE[i].a == Action::COMM && peers > 0) s = 40 + c.sociability / 4;
    // FIGHTは相手が居る時だけ (M7)。
    if (TABLE[i].a == Action::FIGHT && peers == 0) s = 0;
    if (TABLE[i].a == c.action) curScore = s;
    if (s > bestScore) { bestScore = s; best = TABLE[i].a; }
  }
  // IDLEはTABLE外の基礎点30。現行動IDLEにも反映し、離脱・復帰とも+10猶予にする。
  if (c.action == Action::IDLE) curScore = 30;
  // 現行動より明確に良い時だけ切替 (ちらつき防止)
  if (bestScore > curScore + 10) return best;
  return c.action;
}

}  // namespace ai
