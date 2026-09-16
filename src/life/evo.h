#pragma once
// life/evo.h — 進化判定。HW非依存の純粋関数 (FW/検定で共用)。
// P0進化分岐: JUV(7200s)到達時に「お世話スコア×得意形質」で成体morphを決める。
// 血統 (variant=species/12) とfuseは維持し、見た目 (morph=species%12) だけ上書きする。
// Creature本体・48Bパッキングには触らない。お世話カウンタは呼出側 (RTC+NVS) が持つ。
#include <stdint.h>
#include "creature.h"

namespace evo {

static const uint32_t EGG_AGE_MAX = 600;    // 未満はタマゴ (screen.hの表示境界と共有)
static const uint32_t LARVA_AGE_MAX = 7200;  // 未満は幼生。以上で成体 (進化判定点)

// お世話ランク: 0=S 1=A 2=B 3=C
inline uint8_t rankOf(int score) {
  if (score >= 30) return 0;
  if (score >= 10) return 1;
  if (score >= -10) return 2;
  return 3;
}

// 得意形質: 0=INT 1=AGGR 2=CURIO 3=SOC。同値は若番優先 (決定的・再現性あり)。
inline uint8_t domTrait(const Creature& c) {
  uint8_t best = 0;
  uint8_t m = c.intelligence;
  if (c.aggression > m) { m = c.aggression; best = 1; }
  if (c.curiosity > m) { m = c.curiosity; best = 2; }
  if (c.sociability > m) { m = c.sociability; best = 3; }
  return best;
}

// [rank][trait] → morph (0..11)。S=大切にされた姿、C=荒れ姿 (とげ/いわ)。
static const uint8_t TABLE[4][4] = {
  {5, 1, 10, 2},   // S: わっか/つの/きつね/みみ
  {8, 4, 6, 7},    // A: こうら/しま/ひれ/おうかん
  {0, 9, 11, 0},   // B: まる/いわ/さんしょう/まる
  {3, 3, 9, 3},    // C: とげ (CURIOだけいわ)
};

// お世話スコア。bonded/rivalは呼出側が知人帳から数える (aff>=50 / aff<=-50)。
inline int scoreOf(int good, int miss, int ow, int bonded, int rival) {
  return good * 2 - miss * 3 - ow * 5 + bonded * 4 - rival * 2;
}

// 進化適用: variant維持・fuse維持でmorphだけ上書き。戻り値は適用後morph。
inline uint8_t apply(Creature& c, uint8_t morph) {
  if (morph > 11) morph = 0;
  uint16_t variant = (uint16_t)(c.species_id / 12);  // 0..83 (血統)
  c.species_id = (uint16_t)(variant * 12 + morph);
  return morph;
}

}  // namespace evo
