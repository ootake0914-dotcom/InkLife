#pragma once
// env/field.h — 微小現象エンジン。48x12トーラスのBrian's Brain (3状態CA)。
// 起床ごとに数ステップ進め、活動量・対称性を環境指標にする。
// HW非依存・スレッドセーフ設計 (状態は呼出側が持ち、core0ワーカーが回す)。
// Brian's Brain: 1→2→0、0は隣接1が丁度2なら1に。生き生きと動く。
#include <stdint.h>

namespace field {

static const uint8_t W = 48;
static const uint8_t H = 12;

// 2bit/cell packing (Brian's Brainは3状態0,1,2)。144B。旧576B比1/4。
// cyd-particle-life式: 小さい型＋詰め物でRTC/内部RAMを守る。
struct State {
  uint32_t w[(W * H + 15) / 16];
};
static_assert(sizeof(State) == 144, "field State must be 144B");

inline uint8_t get(const State& s, int x, int y) {
  x %= W; if (x < 0) x += W;
  y %= H; if (y < 0) y += H;
  int i = y * W + x;
  return (uint8_t)((s.w[i >> 4] >> ((i & 15) * 2)) & 3);
}

inline void set(State& s, int x, int y, uint8_t v) {
  x %= W; if (x < 0) x += W;
  y %= H; if (y < 0) y += H;
  int i = y * W + x;
  uint32_t m = (uint32_t)3 << ((i & 15) * 2);
  s.w[i >> 4] = (s.w[i >> 4] & ~m) | ((uint32_t)(v & 3) << ((i & 15) * 2));
}

// 簡易xorshift ( genesis用。遺伝のRNGとは別物 )
inline void randomize(State& s, uint32_t seed) {
  uint32_t x = seed ? seed : 0x9E3779B9UL;
  for (int y = 0; y < H; y++)
    for (int xx = 0; xx < W; xx++) {
      x ^= x << 13; x ^= x >> 17; x ^= x << 5;
      set(s, xx, y, (x >> 8) % 4 == 0 ? 1 : 0);  // 25%点火 (旧版と同一系列)
    }
}

inline void step(State& s) {
  State ns;  // 全セル上書きするので初期化不要
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      uint8_t c = get(s, x, y);
      uint8_t v;
      if (c == 1) v = 2;
      else if (c == 2) v = 0;
      else {
        int n = 0;
        for (int dy = -1; dy <= 1; dy++)
          for (int dx = -1; dx <= 1; dx++)
            if ((dx || dy) && get(s, x + dx, y + dy) == 1) n++;
        v = (n == 2) ? 1 : 0;
      }
      set(ns, x, y, v);
    }
  }
  for (unsigned i = 0; i < sizeof(s.w) / sizeof(s.w[0]); i++) s.w[i] = ns.w[i];
}

inline void advance(State& s, int n) {
  for (int i = 0; i < n; i++) step(s);
}

// 活動量 = 状態1の数
inline uint16_t activity(const State& s) {
  uint16_t a = 0;
  for (int i = 0; i < W * H; i++)
    a += (uint16_t)(((s.w[i >> 4] >> ((i & 15) * 2)) & 3) == 1);
  return a;
}

// 対称性0-100 (左右鏡像の一致率)。種分岐の環境圧に使う。
inline uint8_t symmetry(const State& s) {
  int same = 0, total = 0;
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W / 2; x++) {
      total++;
      if (get(s, x, y) == get(s, W - 1 - x, y)) same++;
    }
  return (uint8_t)(same * 100 / total);
}

// 盤面ハッシュ (変化確認用。word走査。旧版と値は変わる)
inline uint32_t hash(const State& s) {
  uint32_t h = 2166136261UL;
  for (unsigned i = 0; i < sizeof(s.w) / sizeof(s.w[0]); i++) {
    h = (h ^ (s.w[i] & 0xFFFF)) * 16777619UL;
    h = (h ^ (s.w[i] >> 16)) * 16777619UL;
  }
  return h;
}

}  // namespace field
