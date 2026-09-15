#pragma once
// life/creature.h — 個体データ。E290固有コードを含まない (移植性のため)。
// パラメータは3群に整理: vitals=生死に直結 / traits=性格・遺伝対象 / identity=個体識別。
// M1時点では tick() を持たない (時間変化はM2)。表示に必要な派生値のみ提供。
#include <Arduino.h>

// 行動 (M1では IDLE/SLEEP のみ使用。M2以降のUtility AIで拡張)
enum class Action : uint8_t { IDLE, SLEEP, EAT, PLAY, EXPLORE, COMM, SEEK, FLEE, APPROACH, FIGHT, BREED };
// 気分は保存しない派生値 (vitalsから毎回計算)。表情ドット絵の切り替えに使う。
enum class Mood : uint8_t { HAPPY, NORMAL, SAD, SLEEPY, SICK };

struct Creature {
  // identity: 世代を超えて引き継ぐもの
  char name[16];
  uint32_t device_id;   // 個体ID (⊆ efuse MAC)。LoRaでも名乗る
  uint16_t species_id;  // 見た目の種 (ドット絵分岐の種)
  uint8_t generation;   // 世代。繁殖で+1 (M8)
  // vitals 0-100: 0や100に張り付くと生死イベントに繋がる (M2)
  uint8_t health;       // 0=死
  uint8_t hunger;       // 高い=空腹。時間で上昇 (M2)
  uint8_t energy;       // 睡眠で回復、行動で消費 (M2/M3)
  uint8_t happiness;
  uint8_t cleanliness;
  // traits 0-100: 基本不変。繁殖時に遺伝＋突然変異 (M8)
  uint8_t intelligence; // 空腹耐性・学習に使う予定
  uint8_t curiosity;    // explore選択率に使う予定
  uint8_t aggression;   // fight/flee判定に使う予定
  uint8_t sociability;  // communicate選択率に使う予定
  uint32_t age_sec;     // 年齢。deep sleepをまたいで加算 (M3/M4)
  Action action;
  bool sleeping;
  uint8_t fuse[4];      // 融合装備 (ポケモン合成式)。gear id、255=空き
  uint8_t habit[3];     // 飽き露出0-100: 0=FOOD 1=PLAY 2=SOCIAL。tickで減衰、刺激で増加 (M10)
};
// cyd式パッキング確認: 16+4+2+10u8+4+1+1+4+3u8=45 payload、ABI末尾padで48。
static_assert(sizeof(Creature) == 48, "Creature must be 48B");

// 新規個体 (第1世代)。名前と種は固定、IDはチップ固有。
inline void creatureInit(Creature& c) {
  strncpy(c.name, "INK", sizeof(c.name));
  c.device_id = (uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFF);
  c.species_id = c.device_id % 1000;
  c.generation = 1;
  c.health = 90; c.hunger = 20; c.energy = 90;
  c.happiness = 70; c.cleanliness = 80;
  // 性格はIDからばらつかせる。同じFWでも個体が違う顔になる (遺伝の布石)。
  c.intelligence = 30 + (c.device_id >> 3) % 50;
  c.curiosity    = 30 + (c.device_id >> 7) % 50;
  c.aggression   = 10 + (c.device_id >> 11) % 40;
  c.sociability  = 30 + (c.device_id >> 15) % 50;
  c.age_sec = 0;
  c.action = Action::IDLE;
  c.sleeping = false;
  for (int i = 0; i < 4; i++) c.fuse[i] = 255;  // 純血開始 (装備なし)
  for (int i = 0; i < 3; i++) c.habit[i] = 0;  // 生まれたては万物が新鮮
}

// 気分派生: 表情と行動選択の入力。優先度順 (病気>睡眠>空腹/不幸>通常)。
inline Mood creatureMood(const Creature& c) {
  if (c.health < 30) return Mood::SICK;
  if (c.sleeping || c.energy < 15) return Mood::SLEEPY;
  if (c.hunger > 70 || c.happiness < 30) return Mood::SAD;
  if (c.happiness > 60 && c.hunger < 50) return Mood::HAPPY;
  return Mood::NORMAL;
}

// 概日リズム (M10): 誕生起点の24h周期。後半8hが夜。壁時計なしで回る体内時計。
inline bool creatureNight(uint32_t age_sec) { return (age_sec % 86400UL) >= 57600UL; }

// 飽き換算 (M10): 刺激の効き = base×(100-露出)%、下限2割 (完全飽和でも少しは嬉しい)。
inline int habGain(int base, uint8_t exposure) {
  int m = 100 - (int)exposure;
  if (m < 20) m = 20;
  return (base * m + 50) / 100;
}

// 性格の一言表示用。最大のtraitを名乗る。
inline const char* creatureNature(const Creature& c) {
  uint8_t m = c.curiosity;
  const char* s = "好奇心旺盛";
  if (c.sociability > m) { m = c.sociability; s = "社交的"; }
  if (c.intelligence > m) { m = c.intelligence; s = "物静か"; }
  if (c.aggression > m) { s = "気が強い"; }
  return s;
}

inline const char* actionName(Action a) {
  switch (a) {
    case Action::IDLE: return "STANDBY";
    case Action::SLEEP: return "SLEEP";
    case Action::EAT: return "FEED";
    case Action::PLAY: return "PLAY";
    case Action::EXPLORE: return "SURVEY";
    case Action::COMM: return "UPLINK";
    case Action::SEEK: return "FORAGE";
    case Action::FLEE: return "EVADE";
    case Action::APPROACH: return "APPROACH";
    case Action::FIGHT: return "COMBAT";
    case Action::BREED: return "BREED";
  }
  return "?";
}

// 時間経過dt秒分の生理変化。呼び出し側はTICK単位 (M2は30秒) で呼ぶ。
// 変化量は「数分で目に見える」デモ用レート。実運用レートはM3以降で調整。
inline void creatureTick(Creature& c, uint32_t dt) {
  uint32_t steps = dt / 30;
  if (steps == 0) steps = 1;
  for (uint32_t i = 0; i < steps; i++) {
    c.age_sec += 30;
    c.hunger = min(100, (int)c.hunger + 2);
    for (int k = 0; k < 3; k++) c.habit[k] = c.habit[k] > 8 ? c.habit[k] - 8 : 0;  // 飽きは6分で醒める
    bool night = creatureNight(c.age_sec);
    if (c.action == Action::SLEEP) {
      c.sleeping = true;
      c.energy = min(100, (int)c.energy + (night ? 12 : 10));  // 夜の眠りは深い
    } else {
      c.sleeping = false;
      c.energy = c.energy > 2 ? c.energy - 2 : 0;
    }
    if (c.action == Action::EAT && c.hunger > 0) {
      c.hunger = c.hunger > 12 ? c.hunger - 12 : 0;  // 自分で食べる分
    }
    if (c.action == Action::PLAY) {
      c.happiness = min(100, (int)c.happiness + 8);
      // energy 1〜4でも消費する (旧if(energy>4)は低ENで無限幸福バグ)。
      // 0に落ちたら次tick以降の衰弱で死ぬ。他分岐と同一の床処理。
      c.energy = c.energy > 4 ? c.energy - 4 : 0;
    } else {
      c.happiness = c.happiness > 0 ? c.happiness - 1 : 0;
    }
    if (((c.age_sec / 30) % 2) == 0 && c.cleanliness > 0) c.cleanliness--;
    // 生死: 飢餓・衰弱で減り、満たされると回復。0で死 (M8で世代交代)。
    // 老衰: 3日を過ぎると毎tick衰弱し、回復しない。死は次世代へ。
    bool old = c.age_sec > 259200;
    if (c.hunger >= 95 || c.energy == 0) {
      if (c.health > 0) c.health--;
    } else if (!old && c.hunger < 50 && c.happiness > 50 && c.health < 100) {
      c.health++;
    }
    if (old && c.health > 0) c.health--;
  }
}

// 行動変化時のイベント文。画面1行・シリアル通知用。
inline const char* actionEvent(Action a) {
  switch (a) {
    case Action::SLEEP: return "ENTER_REST";
    case Action::EAT: return "FEED_START";
    case Action::PLAY: return "PLAY_START";
    case Action::EXPLORE: return "SURVEY_START";
    case Action::COMM: return "SCAN_SIGNAL";
    case Action::IDLE: return "STANDBY";
    default: return "";
  }
}
