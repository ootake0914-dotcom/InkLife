#pragma once
// genetics/breeding.h — 遺伝演算。純粋関数でHW非依存 (単体検定可能)。
// モデル: 各形質は両親のどちらかを受け継ぎ、確率で突然変異。
//  - 70%: 不変 / 15%: ±1 / 10%: ±3 / 5%: ±8 (稀な大変異)
// speciesは上2桁A＋下1桁B＋小変異で混ぜ、見た目の系統が混ざる。
// カオス生態系: 5%で大突然変異 (species全振り直し→別形態が侵入)。
// 12形態 (species%12) ×3系統 (形態%3) のじゃんけん相性あり。
// 融合遺伝子 fuse[4]: スロットi＝ゾーンi (0:HEAD つの/みみ/おうかん / 1:BACK とげ/ひれ/あし /
//   2:BELLY しま/うず/ひげ / 3:AURA まる/わっか/ほし)。各ゾーンは両親の同ゾーン候補
//   (体形＋装備) から1つ継承。敗者は失われる (4枠の選別)。ゾーン内変異5%で多様性を維持。
// 体形も候補に入るため、専用絵を持たない形態 (とげ等) は自形を装備化して正体を表出する。
// 自家繁殖で体形が載るのは仕様 (純血＝装備なし、ではない)。
#include <stdint.h>

namespace genetics {

struct Genes {
  uint8_t intelligence;
  uint8_t curiosity;
  uint8_t aggression;
  uint8_t sociability;
  uint16_t species;
  uint8_t fuse[4];  // 融合装備 (ポケモン合成式)。gear id 0-11、255=空き
};

// 12形態・3系統・じゃんけん相性。系統aが系統bに強い ⇔ (a+1)%3==b。
inline uint8_t morphOf(uint16_t species) { return (uint8_t)(species % 12); }
inline uint8_t familyOf(uint16_t species) { return (uint8_t)(morphOf(species) % 3); }
inline bool familyBeats(uint8_t fa, uint8_t fb) { return fa != fb && (uint8_t)((fa + 1) % 3) == fb; }

// 装備部位ゾーン。同ゾーンは表示1つまで (screen側の優劣と対応)。
inline uint8_t zoneOf(uint8_t gear) {
  switch (gear) {
    case 1: case 2: case 7: return 0;   // HEAD: つの/みみ/おうかん
    case 3: case 6: case 9: return 1;   // BACK: とげ/ひれ/あし(しっぽ)
    case 4: case 8: case 10: return 2;  // BELLY: しま/うず/ひげ
    default: return 3;                  // AURA: まる/わっか/ほし
  }
}

// 0-0xFFFFFFFFを返す乱数関数を注入 (実機=esp_random、検定=任意PRNG)。
typedef uint32_t (*RngFn)(void);

inline uint8_t pick(uint8_t a, uint8_t b, RngFn rng) { return (rng() & 1) ? a : b; }

inline uint8_t mutate(uint8_t v, RngFn rng) {
  uint32_t r = rng() % 100;
  int d = 0;
  if (r < 70) d = 0;
  else if (r < 85) d = (rng() & 1) ? 1 : -1;
  else if (r < 95) d = (int)(rng() % 7) - 3;  // ±3
  else d = (rng() & 1) ? 8 : -8;
  int nv = (int)v + d;
  if (nv < 0) nv = 0;
  if (nv > 100) nv = 100;
  return (uint8_t)nv;
}

inline Genes breed(const Genes& A, const Genes& B, RngFn rng) {
  Genes c;
  c.intelligence = mutate(pick(A.intelligence, B.intelligence, rng), rng);
  c.curiosity = mutate(pick(A.curiosity, B.curiosity, rng), rng);
  c.aggression = mutate(pick(A.aggression, B.aggression, rng), rng);
  c.sociability = mutate(pick(A.sociability, B.sociability, rng), rng);
  uint16_t sp = (uint16_t)((A.species / 10) * 10 + (B.species % 10));
  int dm = (int)(rng() % 21) - 10;
  int nsp = (int)sp + dm;
  nsp %= 1000;
  if (nsp < 0) nsp += 1000;
  if ((rng() % 100) < 5) nsp = (int)(rng() % 1000);  // 大突然変異: 別形態が侵入
  c.species = (uint16_t)nsp;
  // 融合遺伝子 (ゾーン遺伝): スロットz＝ゾーンz。各ゾーンは両親の同ゾーン候補から1つ継承。
  // 候補＝体形 (morphOf)＋fuse装備。候補なし→255 (空き)。敗者は失われる (4枠の選別)。
  // 5%/ゾーンで同ゾーン内変異 (ゾーン不変量を維持しつつ多様性を供給)。
  // F1は両親の体形・装備がゾーン別に混ざる。自家繁殖は各ゾーンを維持 (装備の浸食なし)。
  uint8_t candA[4][6]; uint8_t nA[4] = {0, 0, 0, 0};
  uint8_t candB[4][6]; uint8_t nB[4] = {0, 0, 0, 0};
  auto addA = [&](uint8_t g) {
    if (g > 11) return;
    uint8_t z = zoneOf(g);
    for (uint8_t i = 0; i < nA[z]; i++) if (candA[z][i] == g) return;
    if (nA[z] < 6) candA[z][nA[z]++] = g;
  };
  auto addB = [&](uint8_t g) {
    if (g > 11) return;
    uint8_t z = zoneOf(g);
    for (uint8_t i = 0; i < nB[z]; i++) if (candB[z][i] == g) return;
    if (nB[z] < 6) candB[z][nB[z]++] = g;
  };
  addA(morphOf(A.species));
  for (int i = 0; i < 4; i++) addA(A.fuse[i]);
  addB(morphOf(B.species));
  for (int i = 0; i < 4; i++) addB(B.fuse[i]);
  static const uint8_t ZONE_MEMBERS[4][3] = {{1, 2, 7}, {3, 6, 9}, {4, 8, 10}, {0, 5, 11}};
  for (uint8_t z = 0; z < 4; z++) {
    uint8_t total = (uint8_t)(nA[z] + nB[z]);
    uint8_t v = 255;
    if (total > 0) {
      uint32_t r = rng() % total;
      v = (r < nA[z]) ? candA[z][r] : candB[z][r - nA[z]];
    }
    if ((rng() % 100) < 5) v = ZONE_MEMBERS[z][rng() % 3];
    c.fuse[z] = v;
  }
  return c;
}

}  // namespace genetics
