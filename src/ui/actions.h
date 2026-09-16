#pragma once
// ui/actions.h — ボタン操作の意味付け (M2: BOOT=feed, SIDE=play)。
// 世話の効果量はここに集約。M7で餌在庫制約を足す場合はfeed()を変更する。
#include "../life/creature.h"

namespace ui {

inline const char* feed(Creature& c) {
  if (c.hunger == 0) {
    // 満腹。登録はされたと明示 (STUFFED)。味見分だけ少し嬉しい。
    c.happiness = min(100, (int)c.happiness + habGain(2, c.habit[0]));
    c.action = Action::EAT;
    return "STUFFED";
  }
  c.hunger = c.hunger > 30 ? c.hunger - 30 : 0;
  c.happiness = min(100, (int)c.happiness + habGain(5, c.habit[0]));  // 飽きで効きが落ちる
  c.habit[0] = min(100, (int)c.habit[0] + 25);
  c.cleanliness = c.cleanliness > 15 ? c.cleanliness - 15 : 0;  // 食ったら出す (うんちの種)
  c.action = Action::EAT;
  return "FEED_OK";
}

inline const char* play(Creature& c) {
  if (c.energy < 10) return "LOW_ENERGY";
  c.happiness = min(100, (int)c.happiness + habGain(25, c.habit[1]));
  c.habit[1] = min(100, (int)c.habit[1] + 25);
  c.energy -= 10;
  c.action = Action::PLAY;
  return "PLAY_OK";
}

// 掃除 (同時押し・CLEAN用)。綺麗ならSPOTLESSで何もしない (連打で稼げない)。
inline const char* clean(Creature& c) {
  if (c.cleanliness >= 100) return "SPOTLESS";
  c.cleanliness = 100;
  c.happiness = min(100, (int)c.happiness + 3);  // さっぱり
  c.action = Action::IDLE;
  return "CLEAN_OK";
}

// お薬 (シリアルCURE・PC専用。ボタン逼迫回避)。SICK圏外には効かない (チート防止)。
inline const char* cure(Creature& c) {
  if (c.health >= 50) return "NO_NEED";
  c.health = min(100, (int)c.health + 30);
  c.happiness = c.happiness > 5 ? c.happiness - 5 : 0;  // 苦い
  return "CURE_OK";
}

// 各形態のトレーニング適性 [0]=最得意, [1]=第2適性 (0:INT, 1:AGGR, 2:CURIO, 3:SOC)
static const uint8_t MORPH_TRAIT_APTITUDE[12][2] = {
  {0, 3},  // 0: まる (スライム)   -> INT, SOC
  {1, 2},  // 1: つの (ちびドラ)   -> AGGR, CURIO
  {3, 0},  // 2: みみ (柴犬)       -> SOC, INT
  {1, 2},  // 3: とげ (トゲドラ)   -> AGGR, CURIO
  {2, 1},  // 4: しま (トラ猫)     -> CURIO, AGGR
  {0, 2},  // 5: わっか (フクロウ) -> INT, CURIO
  {2, 3},  // 6: ひれ (お魚)       -> CURIO, SOC
  {3, 0},  // 7: おうかん (カエル) -> SOC, INT
  {0, 3},  // 8: うず (カタツムリ) -> INT, SOC
  {1, 0},  // 9: あし (ゴーレム)   -> AGGR, INT
  {0, 2},  // 10: ひげ (狐)        -> INT, CURIO
  {3, 2}   // 11: ほし (サンショウ)-> SOC, CURIO
};

// トレーニング対象選択 (70%で最得意、30%で第2適性)。train()/inspect共用。
inline uint8_t pickTrainTarget(const Creature& c) {
  uint8_t raw = c.species_id % 12;
  return ((esp_random() % 100) < 70) ? MORPH_TRAIT_APTITUDE[raw][0] : MORPH_TRAIT_APTITUDE[raw][1];
}

// 検査結果の適用 (TRAINと同一利得表。コスト支払い・過労ゲートは呼出側)。
// PERFECTはGREAT上限値+王冠 (表示は呼出側がイベント名"TR:PERFECT!"で判定)。
// 呼出元: シリアルINSPECT (PC側Gキーの反応ゲーム)。実機はダイスtrainを使う。
inline const char* applyInspect(Creature& c, uint8_t target, uint8_t grade) {
  if (target > 3) target = 0;
  if (grade == 4) {  // お手つきは失格 (やる気も少し削る)
    c.happiness = c.happiness > 3 ? c.happiness - 3 : 0;
    c.action = Action::IDLE;
    return "TR:FLYING";
  }
  if (grade == 3) {
    c.action = Action::IDLE;
    return "TR:FAIL";
  }
  uint8_t gain = 0;
  if (grade == 0) {
    gain = 5;
    c.happiness = min(100, (int)c.happiness + 15);
  } else if (grade == 1) {
    gain = 4 + (esp_random() % 2);  // +4〜5 (ダイスGREATと同一)
    c.happiness = min(100, (int)c.happiness + 15);
  } else {
    gain = 2 + (esp_random() % 2);  // +2〜3 (ダイスSUCCESSと同一)
  }
  if (target == 0) c.intelligence = min(100, (int)c.intelligence + gain);
  else if (target == 1) c.aggression = min(100, (int)c.aggression + gain);
  else if (target == 2) c.curiosity = min(100, (int)c.curiosity + gain);
  else if (target == 3) c.sociability = min(100, (int)c.sociability + gain);
  c.habit[1] = min(100, (int)c.habit[1] + 20);  // 手遊びは飽きる (PLAY系)
  c.action = Action::PLAY;  // 大喜び
  return grade == 0 ? "TR:PERFECT!" : grade == 1 ? "TR:GREAT!" : "TR:SUCCESS";
}

// モンスターファーム2式トレーニング (ダイス自動。手動の検査ゲームはapplyInspect側)
// targetTrait: -1=形態適性から自動, 0=INT, 1=AGGR, 2=CURIO, 3=SOC
inline const char* train(Creature& c, int targetTrait = -1) {
  uint8_t target = 0;
  if (targetTrait >= 0 && targetTrait <= 3) {
    target = (uint8_t)targetTrait;
  } else {
    target = pickTrainTarget(c);
  }

  const char* traitNames[] = {"INT", "AGGR", "CURIO", "SOC"};
  const char* tName = traitNames[target];

  // 1. 過労チェック (Energy < 15)
  if (c.energy < 15) {
    c.health = (c.health > 5) ? c.health - 5 : 1;
    c.happiness = (c.happiness > 10) ? c.happiness - 10 : 0;
    c.action = Action::IDLE;
    Serial.printf("+TRAIN res=OVERWORK stat=%s gain=0 hp=%d en=%d\n", tName, c.health, c.energy);
    return "OVERWORK";
  }

  // 2. コスト消費 (特訓による疲労と空腹。simで周回率を測って18->15に緩和)
  c.energy = (c.energy >= 15) ? c.energy - 15 : 0;
  c.hunger = min(100, (int)c.hunger + 12);
  c.happiness = (c.happiness >= 5) ? c.happiness - 5 : 0;

  // 3. 成否ダイスロール (MF2式)
  uint8_t r = esp_random() % 100;

  // (A) サボり判定 (ストレス過多・不満時)
  uint8_t slackChance = (c.happiness < 50) ? (50 - c.happiness) / 3 + 3 : 3;
  if (r < slackChance) {
    c.happiness = min(100, (int)c.happiness + 8);  // サボって少し気分転換
    c.action = Action::PLAY;
    Serial.printf("+TRAIN res=SLACK stat=%s gain=0 en=%d ha=%d\n", tName, c.energy, c.happiness);
    return "TR:SLACK";
  }
  r -= slackChance;

  // (B) 大成功判定 (調子・元気が良いと発生率アップ)
  uint8_t greatChance = (c.happiness >= 70 && c.energy >= 50) ? 20 : 6;
  if (r < greatChance) {
    uint8_t gain = 4 + (esp_random() % 2);  // +4〜5 (旧+3〜4。simで伸びの見えなさを改善)
    if (target == 0) c.intelligence = min(100, (int)c.intelligence + gain);
    else if (target == 1) c.aggression = min(100, (int)c.aggression + gain);
    else if (target == 2) c.curiosity = min(100, (int)c.curiosity + gain);
    else if (target == 3) c.sociability = min(100, (int)c.sociability + gain);
    c.happiness = min(100, (int)c.happiness + 15);
    c.action = Action::PLAY;  // 大喜び
    Serial.printf("+TRAIN res=GREAT stat=%s gain=%d en=%d ha=%d\n", tName, gain, c.energy, c.happiness);
    return "TR:GREAT!";
  }
  r -= greatChance;

  // (C) 成功判定 (Energyが高いほど高確率)
  uint8_t successChance = 40 + (c.energy * 4 / 10);
  if (r < successChance) {
    uint8_t gain = 2 + (esp_random() % 2);  // +2〜3 (旧+1〜2)
    if (target == 0) c.intelligence = min(100, (int)c.intelligence + gain);
    else if (target == 1) c.aggression = min(100, (int)c.aggression + gain);
    else if (target == 2) c.curiosity = min(100, (int)c.curiosity + gain);
    else if (target == 3) c.sociability = min(100, (int)c.sociability + gain);
    c.action = Action::PLAY;
    Serial.printf("+TRAIN res=SUCCESS stat=%s gain=%d en=%d ha=%d\n", tName, gain, c.energy, c.happiness);
    return "TR:SUCCESS";
  }

  // (D) 失敗 (能力上がらず、疲労のみ)
  c.action = Action::IDLE;
  Serial.printf("+TRAIN res=FAIL stat=%s gain=0 en=%d ha=%d\n", tName, c.energy, c.happiness);
  return "TR:FAIL";
}

}  // namespace ui
