#pragma once
// display/screen.h — 296x128 E-Ink描画。左にドット絵、右に8行ステータス。
// E290実機で確認済みの手順のみ (GxEPD2_290_BS / HSPI / 日本語u8g2)。
#include <Arduino.h>
#include <SPI.h>
#include <GxEPD2_BW.h>
#include <U8g2_for_Adafruit_GFX.h>
#include "../hardware/hal.h"
#include "../life/creature.h"
#include "../genetics/breeding.h"  // fuseゾーン優劣 (genetics::zoneOf)
#include "../env/field.h"          // 現象盤ミニ表示 (field::get)

namespace screen {

GxEPD2_BW<GxEPD2_290_BS, GxEPD2_290_BS::HEIGHT> disp(GxEPD2_290_BS(HAL_EPD_CS, HAL_EPD_DC, HAL_EPD_RST, HAL_EPD_BUSY));
SPIClass hspi(HSPI);
U8G2_FOR_ADAFRUIT_GFX u8g2;

// 初期化。戻り値false=BUSY固着で描画不可 (Serial継続は呼出側判断)。
inline bool init() {
  hspi.begin(HAL_EPD_SCK, -1, HAL_EPD_MOSI, HAL_EPD_CS);
  disp.epd2.selectSPI(hspi, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  disp.init(0, true, 2, false);  // diag出力は混入防止で無効
  u8g2.begin(disp);
  u8g2.setFontMode(1);
  u8g2.setForegroundColor(GxEPD_BLACK);
  u8g2.setBackgroundColor(GxEPD_WHITE);
  pinMode(HAL_EPD_BUSY, INPUT);
  unsigned long t0 = millis();
  while (digitalRead(HAL_EPD_BUSY) == HIGH && millis() - t0 < 2000) delay(10);
  return digitalRead(HAL_EPD_BUSY) == LOW;
}

#include "art_ink_idle.h"
#include "art_ink_happy.h"
#include "art_ink_eat.h"
#include "art_ink_sleep.h"
#include "art_ink_sad.h"
#include "art_ink_greet.h"

// 形態別専用アート (全12形態: idle, sleep, eat, happy, sad 完全網羅)
#include "art_ink_m00_idle.h"
#include "art_ink_m00_sleep.h"
#include "art_ink_m00_eat.h"
#include "art_ink_m00_happy.h"
#include "art_ink_m00_sad.h"

#include "art_ink_m01_idle.h"
#include "art_ink_m01_sleep.h"
#include "art_ink_m01_eat.h"
#include "art_ink_m01_happy.h"
#include "art_ink_m01_sad.h"

#include "art_ink_m02_idle.h"
#include "art_ink_m02_sleep.h"
#include "art_ink_m02_eat.h"
#include "art_ink_m02_happy.h"
#include "art_ink_m02_sad.h"

#include "art_ink_m03_idle.h"
#include "art_ink_m03_sleep.h"
#include "art_ink_m03_eat.h"
#include "art_ink_m03_happy.h"
#include "art_ink_m03_sad.h"

#include "art_ink_m04_idle.h"
#include "art_ink_m04_sleep.h"
#include "art_ink_m04_eat.h"
#include "art_ink_m04_happy.h"
#include "art_ink_m04_sad.h"

#include "art_ink_m05_idle.h"
#include "art_ink_m05_sleep.h"
#include "art_ink_m05_eat.h"
#include "art_ink_m05_happy.h"
#include "art_ink_m05_sad.h"

#include "art_ink_m06_idle.h"
#include "art_ink_m06_sleep.h"
#include "art_ink_m06_eat.h"
#include "art_ink_m06_happy.h"
#include "art_ink_m06_sad.h"

#include "art_ink_m07_idle.h"
#include "art_ink_m07_sleep.h"
#include "art_ink_m07_eat.h"
#include "art_ink_m07_happy.h"
#include "art_ink_m07_sad.h"

#include "art_ink_m08_idle.h"
#include "art_ink_m08_sleep.h"
#include "art_ink_m08_eat.h"
#include "art_ink_m08_happy.h"
#include "art_ink_m08_sad.h"

#include "art_ink_m09_idle.h"
#include "art_ink_m09_sleep.h"
#include "art_ink_m09_eat.h"
#include "art_ink_m09_happy.h"
#include "art_ink_m09_sad.h"

#include "art_ink_m10_idle.h"
#include "art_ink_m10_sleep.h"
#include "art_ink_m10_eat.h"
#include "art_ink_m10_happy.h"
#include "art_ink_m10_sad.h"

#include "art_ink_m11_idle.h"
#include "art_ink_m11_sleep.h"
#include "art_ink_m11_eat.h"
#include "art_ink_m11_happy.h"
#include "art_ink_m11_sad.h"

#include "art_parts.h"

// 12形態インデックスを完成済み大形態へ正規化 (装備アンカー用)
static const uint8_t MORPH_5_MAP[12] = {
  0, // 0: まる (スライム)
  1, // 1: つの (ちびドラゴン)
  2, // 2: みみ (柴犬)
  1, // 3: とげ -> ドラゴン
  4, // 4: しま (トラ猫)
  2, // 5: わっか -> 柴犬 (装備アンカー用)
  7, // 6: ひれ -> カエル王子
  7, // 7: おうかん (カエル王子)
  0, // 8: うず -> スライム
  1, // 9: あし -> ドラゴン
  2, // 10: ひげ -> 柴犬 (装備アンカー用)
  0  // 11: ほし -> スライム
};

static const unsigned char* const MORPH_IDLE_XBM[12] = {
  ink_m00_idle_xbm,  // 0: まる (スライム)
  ink_m01_idle_xbm,  // 1: つの (ちびドラゴン)
  ink_m02_idle_xbm,  // 2: みみ (柴犬)
  ink_m03_idle_xbm,  // 3: とげ (専用絵で独立)
  ink_m04_idle_xbm,  // 4: しま (トラ猫)
  ink_m05_idle_xbm,  // 5: わっか (フクロウ・専用絵で独立)
  ink_m06_idle_xbm,  // 6: ひれ (独立)
  ink_m07_idle_xbm,  // 7: おうかん (カエル王子)
  ink_m08_idle_xbm,  // 8: うず (独立)
  ink_m09_idle_xbm,  // 9: あし (独立)
  ink_m10_idle_xbm,  // 10: ひげ (狐・専用絵で独立)
  ink_m11_idle_xbm,  // 11: ほし (独立)
};

// 成長サイズ: 64px(誕生)→96px(約3時間で成体)。連続変化で有機的に育つ。
inline int growthSize(uint32_t age_sec) {
  uint32_t s = 64 + age_sec / 270;  // 270秒で1px成長
  if (s > 96) s = 96;
  return (int)s;
}

// XBM(96x96)をdst正方形に最近傍スケール描画。96枠の中央寄せ。
// setピクセルのみdrawPixel (白はskip)。sx/syはdst毎にLUT化し除算を排除。
// block転送版 (1152B展開＋drawXBitmap) も試したが、白skip無し＋二重走査で2.2倍遅かったため不採用 (BENCH実測)。
static int sclCachedDst = -1;
static uint8_t sclSX[96], sclSY[96];
inline void drawXbmScaled(const unsigned char* art, int ox, int oy, int dst) {
  if (sclCachedDst != dst) {  // 成長は270秒で1px。作り直しは稀
    sclCachedDst = dst;
    for (int i = 0; i < dst; i++) {
      sclSX[i] = (uint8_t)((i * 96) / dst);
      sclSY[i] = (uint8_t)((i * 96) / dst);
    }
  }
  int px = ox + (96 - dst) / 2, py = oy + (96 - dst) / 2;
  for (int dy = 0; dy < dst; dy++) {
    int row = sclSY[dy] * 12;
    for (int dx = 0; dx < dst; dx++) {
      int sx = sclSX[dx];
      if (art[row + (sx >> 3)] & (1 << (sx & 7))) disp.drawPixel(px + dx, py + dy, GxEPD_BLACK);
    }
  }
}
// 形態別専用アクションアート取得 (全12形態完全網羅)
inline const unsigned char* getMorphActionArt(uint8_t mid, Action a, Mood m) {
  bool isSleep = (a == Action::SLEEP || m == Mood::SLEEPY);
  bool isEat = (a == Action::EAT);
  bool isHappy = (a == Action::PLAY || m == Mood::HAPPY);
  bool isSad = (m == Mood::SAD || m == Mood::SICK);

  switch (mid) {
    case 0:  // まる (スライム)
      if (isSleep) return ink_m00_sleep_xbm;
      if (isEat) return ink_m00_eat_xbm;
      if (isHappy) return ink_m00_happy_xbm;
      if (isSad) return ink_m00_sad_xbm;
      break;
    case 1:  // つの (ちびドラゴン)
      if (isSleep) return ink_m01_sleep_xbm;
      if (isEat) return ink_m01_eat_xbm;
      if (isHappy) return ink_m01_happy_xbm;
      if (isSad) return ink_m01_sad_xbm;
      break;
    case 2:  // みみ (柴犬)
      if (isSleep) return ink_m02_sleep_xbm;
      if (isEat) return ink_m02_eat_xbm;
      if (isHappy) return ink_m02_happy_xbm;
      if (isSad) return ink_m02_sad_xbm;
      if (a == Action::COMM) return ink_greet_xbm;
      break;
    case 3:  // とげ (トゲドラゴン)
      if (isSleep) return ink_m03_sleep_xbm;
      if (isEat) return ink_m03_eat_xbm;
      if (isHappy) return ink_m03_happy_xbm;
      if (isSad) return ink_m03_sad_xbm;
      break;
    case 4:  // しま (トラ猫)
      if (isSleep) return ink_m04_sleep_xbm;
      if (isEat) return ink_m04_eat_xbm;
      if (isHappy) return ink_m04_happy_xbm;
      if (isSad) return ink_m04_sad_xbm;
      break;
    case 5:  // わっか (フクロウ)
      if (isSleep) return ink_m05_sleep_xbm;
      if (isEat) return ink_m05_eat_xbm;
      if (isHappy) return ink_m05_happy_xbm;
      if (isSad) return ink_m05_sad_xbm;
      break;
    case 6:  // ひれ (お魚クリーチャー)
      if (isSleep) return ink_m06_sleep_xbm;
      if (isEat) return ink_m06_eat_xbm;
      if (isHappy) return ink_m06_happy_xbm;
      if (isSad) return ink_m06_sad_xbm;
      break;
    case 7:  // おうかん (カエル王子)
      if (isSleep) return ink_m07_sleep_xbm;
      if (isEat) return ink_m07_eat_xbm;
      if (isHappy) return ink_m07_happy_xbm;
      if (isSad) return ink_m07_sad_xbm;
      break;
    case 8:  // うず (カタツムリ)
      if (isSleep) return ink_m08_sleep_xbm;
      if (isEat) return ink_m08_eat_xbm;
      if (isHappy) return ink_m08_happy_xbm;
      if (isSad) return ink_m08_sad_xbm;
      break;
    case 9:  // あし (ゴーレム)
      if (isSleep) return ink_m09_sleep_xbm;
      if (isEat) return ink_m09_eat_xbm;
      if (isHappy) return ink_m09_happy_xbm;
      if (isSad) return ink_m09_sad_xbm;
      break;
    case 10:  // ひげ (狐)
      if (isSleep) return ink_m10_sleep_xbm;
      if (isEat) return ink_m10_eat_xbm;
      if (isHappy) return ink_m10_happy_xbm;
      if (isSad) return ink_m10_sad_xbm;
      break;
    case 11:  // ほし (サンショウウオ)
      if (isSleep) return ink_m11_sleep_xbm;
      if (isEat) return ink_m11_eat_xbm;
      if (isHappy) return ink_m11_happy_xbm;
      if (isSad) return ink_m11_sad_xbm;
      break;
    default:
      break;
  }
  return nullptr;
}

// 各形態がキメラパーツを装着する際のアンカーベース形態 (0:スライム, 1:ドラゴン, 2:犬, 4:猫, 7:カエル, 10:狐)
static const uint8_t ANCHOR_BASE_MAP[12] = {
  0,  // 0: スライム
  1,  // 1: ドラゴン
  2,  // 2: 柴犬
  1,  // 3: うろこ -> ドラゴン
  4,  // 4: トラ猫
  2,  // 5: わっか/フクロウ
  1,  // 6: はね -> ドラゴン
  7,  // 7: カエル王子
  0,  // 8: うずまき -> スライム
  4,  // 9: しっぽ -> トラ猫
  10, // 10: 狐
  0   // 11: ほし -> スライム
};

inline void sprite(const Creature& c, Mood m, int ox, int oy) {
  const unsigned char* art = nullptr;
  Action a = c.action;
  uint8_t raw = c.species_id % 12;
  uint8_t mid = ANCHOR_BASE_MAP[raw];
  // 生形態の専用アクション絵 (0,1,2,4,5,7,10等) を取得
  const unsigned char* dedicated = getMorphActionArt(raw, a, m);

  if (dedicated) {
    art = dedicated;
  } else {
    // 他形態に化けさせず、自前のIDLE絵を維持 (未対応形態はオーバーレイ演出で表現)
    art = MORPH_IDLE_XBM[raw];
  }

  int dst = growthSize(c.age_sec);
  drawXbmScaled(art, ox, oy, dst);
  // 進化マーカー: 96空間で定義→成長サイズに追従。長さ・数は形質値に比例。
  // 12形態 (species%12)。顔中央 (x30-66,y30-70) は避けて配置。
  int bx = ox + (96 - dst) / 2, by = oy + (96 - dst) / 2;
  auto SC = [&](int v) { return (v * dst) / 96; };
  auto dot = [&](int x, int y, int w, int h) {
    disp.fillRect(bx + SC(x), by + SC(y), max(1, SC(w)), max(1, SC(h)), GxEPD_BLACK);
  };
  auto ln = [&](int x0, int y0, int x1, int y1) {
    disp.drawLine(bx + SC(x0), by + SC(y0), bx + SC(x1), by + SC(y1), GxEPD_BLACK);
  };
  auto ring = [&](int x, int y, int r) {
    disp.drawCircle(bx + SC(x), by + SC(y), max(1, SC(r)), GxEPD_BLACK);
  };
  auto tri = [&](int x0, int y0, int x1, int y1, int x2, int y2) {
    disp.fillTriangle(bx + SC(x0), by + SC(y0), bx + SC(x1), by + SC(y1), bx + SC(x2), by + SC(y2), GxEPD_WHITE);
    disp.drawTriangle(bx + SC(x0), by + SC(y0), bx + SC(x1), by + SC(y1), bx + SC(x2), by + SC(y2), GxEPD_BLACK);
  };
  // 融合表示: 自形態＋fuse装備の全部載せ (Infinite Fusion式: 象徴だけ借りる)。
  // 同ゾーン競合の敗者は非表示 (選別。Niche式の部位優劣。変異・交配で再供給される)。
  // 画像を刻んだ遺伝パーツの境界マスク付きブレンド描画
  auto drawPart = [&](const uint8_t* bmp, const uint8_t* mask, uint8_t pw, uint8_t ph, int px, int py) {
    if (!bmp) return;
    int wb = (pw + 7) / 8;
    // パス1: 白マスクで下地をクリア (余計な線をくり抜いて自然に繋ぐ)
    if (mask) {
      for (int y = 0; y < ph; y++) {
        int sy = py + y;
        if (sy < 0 || sy >= 96) continue;
        int dy = by + SC(sy);
        for (int x = 0; x < pw; x++) {
          int sx = px + x;
          if (sx < 0 || sx >= 96) continue;
          int dx = bx + SC(sx);
          if (pgm_read_byte(&mask[y * wb + (x >> 3)]) & (1 << (x & 7))) {
            disp.drawPixel(dx, dy, GxEPD_WHITE);
          }
        }
      }
    }
    // パス2: 黒ピクセルを描画 (輪郭を綺麗に接続)
    for (int y = 0; y < ph; y++) {
      int sy = py + y;
      if (sy < 0 || sy >= 96) continue;
      int dy = by + SC(sy);
      for (int x = 0; x < pw; x++) {
        int sx = px + x;
        if (sx < 0 || sx >= 96) continue;
        int dx = bx + SC(sx);
        if (pgm_read_byte(&bmp[y * wb + (x >> 3)]) & (1 << (x & 7))) {
          disp.drawPixel(dx, dy, GxEPD_BLACK);
        }
      }
    }
  };

  // 融合表示: 刻んだピクセルアートパーツによる美しいキメラ描画
  // 同系統の自前パーツはスキップし、他形態から遺伝した特徴のみを最適な接合座標にマウント
  // ビットマップ物は parts::PART_ROWS 駆動。手続き型 (0/4/8/11) のみ直書き。
  auto gear = [&](uint8_t id) {
    if (id == mid) return;  // 自前パーツは本体アートに描画済み
    if (id == 0) {  // まる (スライムのハイライト水玉)
      dot(14, 76, 5, 5); dot(78, 76, 5, 5);
      return;
    }
    if (id == 4) {  // しま (トラ猫の縞)
      dot(12, 70, 14, 3); dot(70, 70, 14, 3);
      return;
    }
    if (id == 8) {  // うず (お腹の渦巻き。中央下は避けてへそ位置に)
      ring(48, 66, 3); ring(48, 66, 6);
      return;
    }
    if (id == 11) {  // ほし (四隅のキラキラ星屑)
      const int8_t st[][2] = {{14,14},{82,14},{14,82},{82,82}};
      int n = min(4, 2 + (int)c.happiness * 2 / 100);
      for (int i = 0; i < n; i++) { dot(st[i][0] - 4, st[i][1] - 1, 9, 3); dot(st[i][0] - 1, st[i][1] - 4, 3, 9); }
      return;
    }
    for (unsigned i = 0; i < sizeof(parts::PART_ROWS) / sizeof(parts::PART_ROWS[0]); i++) {
      const parts::PartRow& r = parts::PART_ROWS[i];
      if (r.gear != id) continue;
      for (uint8_t a = 0; a < r.anchorCount; a++) {
        if (r.anchors[a].mid != mid && r.anchors[a].mid != 255) continue;
        drawPart(r.bmp, r.mask, r.w, r.h, r.anchors[a].x, r.anchors[a].y);
        break;  // 1行1ブリット
      }
    }
  };

  // 融合遺伝子 fuse[0..3] を順に描画。新保存はスロットi＝ゾーンi。
  // 旧保存の同ゾーン重複は先勝ちで1つだけ出す (ゾーン優劣)。
  // raw自身（c.species_id%12）と正規化midはスキップ (本体アートに描画済み、または専用絵で独立)。
  uint8_t wonZoneMask = 0;
  for (int i = 0; i < 4; i++) {
    uint8_t f = c.fuse[i];
    if (f > 11 || f == raw || f == mid) continue;
    bool dup = false;
    for (int j = 0; j < i; j++) if (c.fuse[j] == f) { dup = true; break; }
    if (dup) continue;
    uint8_t z = genetics::zoneOf(f);
    if (wonZoneMask & (uint8_t)(1 << z)) continue;  // 同部位は1装備まで
    wonZoneMask |= (uint8_t)(1 << z);
    gear(f);
  }

  // アクション演出オーバーレイ (専用アクション絵を持たない形態向け。dedicatedがある場合は自前画像で表現)
  if (!dedicated) {
    if (a == Action::SLEEP || m == Mood::SLEEPY) {
      // 右上に浮かぶ「Zzz」
      ln(76, 8, 86, 8); ln(86, 8, 76, 18); ln(76, 18, 86, 18);
      ln(68, 18, 74, 18); ln(74, 18, 68, 24); ln(68, 24, 74, 24);
      ln(60, 26, 64, 26); ln(64, 26, 60, 30); ln(60, 30, 64, 30);
    } else if (a == Action::EAT) {
      // 右下の足元にフードボウル (皿とごはん)
      disp.fillRect(bx + SC(66), by + SC(82), max(1, SC(26)), max(1, SC(10)), GxEPD_WHITE);
      disp.drawRect(bx + SC(66), by + SC(82), max(1, SC(26)), max(1, SC(10)), GxEPD_BLACK);
      disp.fillRect(bx + SC(64), by + SC(80), max(1, SC(30)), max(1, SC(3)), GxEPD_BLACK);
      dot(72, 78, 2, 2); dot(76, 76, 2, 2); dot(80, 78, 2, 2); dot(84, 77, 2, 2); dot(78, 80, 2, 2);
    } else if (a == Action::PLAY || m == Mood::HAPPY) {
      // 左上に音符♪、右上にキラキラ★
      ring(12, 20, 2);
      ln(14, 12, 14, 20);
      ln(14, 12, 18, 14);
      ln(82, 8, 82, 16); ln(78, 12, 86, 12);
      ln(88, 22, 88, 28); ln(85, 25, 91, 25);
    } else if (m == Mood::SAD || m == Mood::SICK) {
      // 涙と右下の絆創膏
      dot(22, 45, 3, 4); dot(21, 51, 3, 4);
      disp.fillRect(bx + SC(74), by + SC(76), max(1, SC(14)), max(1, SC(10)), GxEPD_WHITE);
      disp.drawRect(bx + SC(74), by + SC(76), max(1, SC(14)), max(1, SC(10)), GxEPD_BLACK);
      ln(81, 77, 81, 85); ln(77, 81, 85, 81);
    } else if (a == Action::COMM) {
      // 通信アンテナ波紋
      ring(84, 14, 4); ring(84, 14, 8); ring(84, 14, 12);
    }
  }
}

inline const char* morphName(uint16_t species) {
  uint8_t raw = species % 12;
  switch (raw) {
    case 0: return "SLIME";
    case 1: return "DRAGON";
    case 2: return "SHIBA";
    case 3: return "SPINE";
    case 4: return "CAT";
    case 5: return "HALO";
    case 6: return "FIN";
    case 7: return "FROG";
    case 8: return "SPIRAL";
    case 9: return "LEG";
    case 10: return "WHISKER";
    case 11: return "STAR";
    default: return "PET";
  }
}
inline void morphTag(const Creature& c, char* b) {  // b[10]。cyd式: 戻りString禁止
  snprintf(b, 10, "%s-%02d", morphName(c.species_id), c.species_id % 12);
}

inline const char* stageName(uint32_t age_sec) {
  if (age_sec < 600) return "LARVA";
  if (age_sec < 7200) return "JUV";
  if (age_sec < 43200) return "ADULT";
  return "ELDER";
}

// 8px英字HUD用。yはベースライン。String不使用 (heap断片化防止)。
inline void textEN(int x, int y, const char* s) {
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(x, y, s);
}
inline void fmtHMS(uint32_t sec, char* b) {  // b[10]
  uint32_t h = sec / 3600; if (h > 99) h = 99;
  snprintf(b, 10, "%02lu:%02lu:%02lu", (unsigned long)h, (unsigned long)(sec / 60) % 60, (unsigned long)sec % 60);
}
inline void fmt3(int v, char* b) {  // b[4]
  snprintf(b, 4, "%03d", v);
}
// ミニバー (x, ytop, w)。高さ6。
inline void pbar(int x, int ytop, int w, int v) {
  disp.drawRect(x, ytop, w, 6, GxEPD_BLACK);
  int fw = constrain((w - 2) * v / 100, 0, w - 2);
  if (fw > 0) disp.fillRect(x + 1, ytop + 1, fw, 4, GxEPD_BLACK);
}
// 最大形質のコード＋値 (例: CUR 082)。b[8]
inline void traitLabel(const Creature& c, char* b) {
  uint8_t m = c.curiosity; const char* s = "CUR";
  if (c.sociability > m) { m = c.sociability; s = "SOC"; }
  if (c.intelligence > m) { m = c.intelligence; s = "INT"; }
  if (c.aggression > m) { m = c.aggression; s = "AGG"; }
  snprintf(b, 8, "%s %03d", s, m);
}

// イベントログ (直近3件。揮発・セッション内のみ)。
static char evLog[3][28];
static uint32_t evLogAge[3];
inline void pushLog(const char* e, uint32_t age) {
  strncpy(evLog[2], evLog[1], 27); evLog[2][27] = 0; evLogAge[2] = evLogAge[1];
  strncpy(evLog[1], evLog[0], 27); evLog[1][27] = 0; evLogAge[1] = evLogAge[0];
  strncpy(evLog[0], e, 27); evLog[0][27] = 0; evLogAge[0] = age;
}
inline void logLine(int i, char* b) {  // b[28]
  if (!evLog[i][0]) { b[0] = 0; return; }
  char h[10]; fmtHMS(evLogAge[i], h);
  snprintf(b, 28, ">T+%s %s", h, evLog[i]);
}

// 初誕生スプラッシュ (NVSにも居ない完全新規時のみ)。
inline void splash(const Creature& c) {
  disp.setRotation(1);
  disp.setFullWindow();
  disp.firstPage();
  do {
    disp.fillScreen(GxEPD_WHITE);
    disp.drawRect(0, 0, 296, 128, GxEPD_BLACK);
    char l1[28], l2[16], mt[10];
    morphTag(c, mt);
    snprintf(l1, sizeof(l1), "SPEC %s // GEN-01", c.name);
    snprintf(l2, sizeof(l2), "MORPH %s", mt);
    textEN(88, 34, "INK-LIFE SYSTEM");
    textEN(78, 58, l1);
    textEN(92, 80, l2);
    textEN(108, 104, ">> AWAKEN");
  } while (disp.nextPage());
}

inline const char* stateCode(Mood m) {
  switch (m) {
    case Mood::HAPPY: return "OPTIMAL";
    case Mood::SAD: return "STRESSED";
    case Mood::SLEEPY: return "REST";
    case Mood::SICK: return "CRITICAL";
    default: return "NOMINAL";
  }
}

// 現象盤ミニ表示 (48x12を1px/cellで50x14枠に)。発火=黒、減衰=市松(灰)、静寂=白。
// Brian's Brainの生き生きがE-Inkの隅で見える。描画576pxと激安。
inline void fieldMini(const field::State& f, int ox, int oy) {
  disp.drawRect(ox, oy, 50, 14, GxEPD_BLACK);
  disp.fillRect(ox + 1, oy + 1, 48, 12, GxEPD_WHITE);
  for (int y = 0; y < 12; y++)
    for (int x = 0; x < 48; x++) {
      uint8_t v = field::get(f, x, y);
      if (v == 1) disp.drawPixel(ox + 1 + x, oy + 1 + y, GxEPD_BLACK);
      else if (v == 2 && ((x + y) & 1) == 0) disp.drawPixel(ox + 1 + x, oy + 1 + y, GxEPD_BLACK);
    }
}

// 画面全体描画。full=trueでフル更新。friends=知人数 (0で非表示)。fld=nullで現象窓なし。
inline void draw(const Creature& c, const char* event, bool full, uint8_t friends = 0,
                 const field::State* fld = nullptr) {
  disp.setRotation(1);
  if (full) disp.setFullWindow();
  else disp.setPartialWindow(0, 0, disp.width(), disp.height());
  Mood m = creatureMood(c);
  char idb[9], gb[5], mt[10], hms[10];
  snprintf(idb, sizeof(idb), "%08lX", (unsigned long)c.device_id);
  snprintf(gb, sizeof(gb), "G%02d", c.generation);
  morphTag(c, mt);
  fmtHMS(c.age_sec, hms);
  disp.firstPage();
  do {
    disp.fillScreen(GxEPD_WHITE);
    disp.drawRect(0, 0, 296, 128, GxEPD_BLACK);
    // 標本窓
    char up[13], sp[16], idl[24], row[24], l0[28], l1[28], tr[8];
    snprintf(up, sizeof(up), "T+%s", hms);
    textEN(6, 11, "SPECIMEN");
    textEN(236, 11, up);
    sprite(c, m, 4, 16);
    disp.drawLine(4, 16, 12, 16, GxEPD_BLACK); disp.drawLine(4, 16, 4, 24, GxEPD_BLACK);
    disp.drawLine(100, 16, 92, 16, GxEPD_BLACK); disp.drawLine(100, 16, 100, 24, GxEPD_BLACK);
    disp.drawLine(4, 112, 12, 112, GxEPD_BLACK); disp.drawLine(4, 112, 4, 104, GxEPD_BLACK);
    disp.drawLine(100, 112, 92, 112, GxEPD_BLACK); disp.drawLine(100, 112, 100, 104, GxEPD_BLACK);
    snprintf(sp, sizeof(sp), "%s %s", gb, mt);
    textEN(6, 123, sp);
    // モニタ
    disp.drawLine(108, 4, 108, 124, GxEPD_BLACK);
    int tx = 114;
    if (friends > 0) snprintf(idl, sizeof(idl), "ID %s %s P%u", idb, gb, friends);
    else snprintf(idl, sizeof(idl), "ID %s %s", idb, gb);
    textEN(tx, 13, idl);
    snprintf(row, sizeof(row), "HP  %03d", c.health);
    textEN(tx, 25, row); pbar(tx + 48, 19, 70, c.health);
    snprintf(row, sizeof(row), "SAT %03d", 100 - c.hunger);
    textEN(tx, 37, row); pbar(tx + 48, 31, 70, 100 - c.hunger);
    snprintf(row, sizeof(row), "EN  %03d", c.energy);
    textEN(tx, 49, row); pbar(tx + 48, 43, 70, c.energy);
    snprintf(row, sizeof(row), "HA  %03d", c.happiness);
    textEN(tx, 61, row); pbar(tx + 48, 55, 70, c.happiness);
    snprintf(row, sizeof(row), "ACT %s", actionName(c.action));
    textEN(tx, 73, row);
    if (fld) {  // 現象窓 (ACT行右の空きに48x12盤＋活動量)
      fieldMini(*fld, 240, 60);
      char fb[10];
      snprintf(fb, sizeof(fb), "FLD %3d", field::activity(*fld));
      textEN(198, 73, fb);
    }
    traitLabel(c, tr);
    snprintf(row, sizeof(row), "ST %s TRT %s", stateCode(m), tr);
    textEN(tx, 85, row);
    snprintf(row, sizeof(row), "STG %s %s%s", stageName(c.age_sec), hms,
             creatureNight(c.age_sec) ? " NGT" : " DAY");
    textEN(tx, 97, row);
    logLine(0, l0); textEN(tx, 110, l0);
    logLine(1, l1); textEN(tx, 121, l1);
  } while (disp.nextPage());
}

// パネルのDC-DC昇圧回路等を完全休止させ漏電を防ぐ
inline void hibernate() {
  disp.hibernate();
}

}  // namespace screen
