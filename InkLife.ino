// Ink Life — E-Ink LoRa人工生命 (Milestone 9: 現象エンジン＋電波エントロピー遺伝＋デュアルコア)
// FQBN: esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB
#include <Arduino.h>
#include "src/hardware/hal.h"
#include "src/life/creature.h"
#include "src/life/evo.h"
#include "src/behavior/ai.h"
#include "src/ui/actions.h"
#include "src/time/clock.h"
#include "src/power/sleep.h"
#include "src/storage/store.h"
#include "src/radio/mesh.h"
#include "src/genetics/breeding.h"
#include "src/core/jobs.h"
#include "src/display/screen.h"

namespace {
// deep sleepをまたぐ状態。電源断で消える (NVSが保険)。
RTC_DATA_ATTR uint32_t rtcMagic = 0;
RTC_DATA_ATTR Creature rtcCre;
RTC_DATA_ATTR uint64_t rtcLastUs = 0;
RTC_DATA_ATTR uint32_t rtcBoots = 0;
RTC_DATA_ATTR char rtcEvent[32] = {0};
RTC_DATA_ATTR uint32_t rtcUnix = 0;  // 最後にTIMEで知ったunix秒 (不在計算用)
RTC_DATA_ATTR uint8_t rtcPendingEvt = 0;  // 未送EVENT符号 (誕生時に1、進化時に2。次無線で送出)
// お世話カウンタ (進化判定用。Creature本体48Bには入れない別枠。次世代でリセット)
RTC_DATA_ATTR uint16_t rtcCareGood = 0;  // FEED_OK/PLAY_OK回数
RTC_DATA_ATTR uint16_t rtcCareMiss = 0;  // 飢餓放置tick数 (hunger>=95)
RTC_DATA_ATTR uint16_t rtcOverwork = 0;  // OVERWORK回数
RTC_DATA_ATTR uint32_t rtcOhayoDay = 0;  // おはよう済みのJST日付 (朝ボーナス1日1回。停電で忘れる分には二度貰えるだけ)
RTC_DATA_ATTR field::State rtcField;      // 現象盤 (144B。旧コメント576Bは1bit時代の名残)
RTC_DATA_ATTR bool rtcFieldInit = false;  // 盤面初期化済み
RTC_DATA_ATTR bool rtcAllowBle = true;    // BLEスキャン許可 (NVSキルスイッチ連動)
// 知人帳 (M6): 聞いた他個体を最大6件記憶。電源断で忘れる (引っ越し扱い)。
// cyd式パッキング: rssiはdBm整数、countは255飽和。28B/件 (ABI末尾pad含む)。
struct PeerInfo {
  uint32_t did;
  uint32_t lastAge;  // 最終目撃時の自年齢
  uint16_t species;
  uint8_t gen;
  int8_t rssi;       // dBm整数 (-120〜0)
  uint8_t count;     // 累計受信回数 (255飽和)
  uint8_t ti, cu, ag, so;  // 形質 (v2 STATUS受信時のみ有効)
  bool hasTr;
  bool hasSpecies;  // HELLOで種既知か (STATUSのみ知人はfalse)
  int8_t aff;       // 好感度-100〜+100。tickで0へ減衰、停電で忘れる (M10)
  uint8_t fz[4];    // 融合遺伝子 (v3 STATUS受信時のみ有効。255=空き)
  bool hasFz;
};
static_assert(sizeof(PeerInfo) == 28, "PeerInfo must be 28B (25B payload + 3B pad)");
RTC_DATA_ATTR PeerInfo rtcPeers[6];
RTC_DATA_ATTR uint8_t rtcPeerN = 0;
RTC_DATA_ATTR uint32_t rtcLastDispHash = 0;  // 最終転送時の表示hash (deep sleep越えのskip判定用)
RTC_DATA_ATTR bool rtcHaveDrawn = false;     // 一度でも転送済みか
static const bool SLEEP_ENABLE = false;  // 通常はOFF (常時起動)。電池運用でtrueに。
static const uint32_t RTC_MAGIC = 0x494E4B53;  // "INKS" (表示hash追加で更新。旧RTC破棄→NVS復元)
static const uint32_t TICK_SEC = 30;
static const uint32_t CATCHUP_MAX_STEPS = 24;  // 24*30s=12分相当で打ち止め (長期不在は甘め。旧コメント「12時間分」は誤り)
bool gDispOk = false;
bool gStayAwake = false;  // trueでsleepせず常時起動 (開発・PC接続用)
unsigned long gStayTick = 0;
static unsigned long gLastDrawMs = 0;  // 最終描画時刻 (tick重複抑制用)
uint32_t gDrawCount = 0;   // 描画回数 (PX監査用。再起動で0)
uint32_t gStallCount = 0;  // 3秒超え描画の回数 (パネル失速検出。GxEPD2はtimeout突破する)
uint32_t gSkipCount = 0;   // 内容不変で省略した転送回数 (PX監査用。再起動で0)
uint32_t gFullCount = 0;   // full転送回数 (PX監査用。残像清掃の周期確認用)
static uint32_t gXferCount = 0;  // 実転送数 (stay-awake路のfull周期用)
static const uint32_t PERIODIC_FULL_EVERY = 12;  // 12転送毎にfullで残像清掃 (通常約25分毎)
uint32_t gEventSeq = 0;    // setEvent毎に+1 (単調)。描画要否判定用。再起動で0
static Action gDrawnAction = Action::IDLE;  // 最終転送時のスナップ (通常tickの間引き用)
static Mood gDrawnMood = Mood::NORMAL;
static uint32_t gDrawnEventSeq = 0;
static uint32_t gTicksSinceDraw = 0;
static const uint32_t ROUTINE_DRAW_TICKS = 4;  // 通常tickは4tick毎 (約2分毎) のみ転送。重要変化は即時
uint8_t gPendBtn = 0;  // 受信窓中の押下保持 (取りこぼし防止)
void stayDraw(bool full, bool force = false);  // 後方定義 (loop中の描画は時刻を刻む)

void logLife() {
  char buf[128];
  snprintf(buf, sizeof(buf), "+LIFE age=%u hp=%u hu=%u en=%u ha=%u act=%s gen=%u tr=%u,%u,%u,%u",
           (unsigned)rtcCre.age_sec, (unsigned)rtcCre.health, (unsigned)rtcCre.hunger,
           (unsigned)rtcCre.energy, (unsigned)rtcCre.happiness,
           actionName(rtcCre.action), (unsigned)rtcCre.generation,
           (unsigned)rtcCre.intelligence, (unsigned)rtcCre.curiosity,
           (unsigned)rtcCre.aggression, (unsigned)rtcCre.sociability);
  Serial.println(buf);
}

// 配偶子探索: 好感度最大の形質既知知人 (同点は最新)。居なければnullptr (自家系)。
// 好きな相手と繁殖する (M10)。嫌いでも拒否はしない (種の存続優先)。
void setEvent(const char* e);  // 後方定義
const genetics::Genes* findMateGenes() {
  static genetics::Genes g;
  int best = -1;
  for (uint8_t i = 0; i < rtcPeerN; i++) {
    if (!rtcPeers[i].hasTr) continue;
    if (best < 0 || rtcPeers[i].aff > rtcPeers[best].aff ||
        (rtcPeers[i].aff == rtcPeers[best].aff && rtcPeers[i].lastAge > rtcPeers[best].lastAge))
      best = i;
  }
  if (best < 0) return nullptr;
  g.intelligence = rtcPeers[best].ti;
  g.curiosity = rtcPeers[best].cu;
  g.aggression = rtcPeers[best].ag;
  g.sociability = rtcPeers[best].so;
  // STATUSのみ知人は種未知。ones-digit偏り防止に自種で代用 (見た目系統のみに影響)
  g.species = rtcPeers[best].hasSpecies ? rtcPeers[best].species : rtcCre.species_id;
  // v3 STATUSのfuseを継承。v1/v2旧FW相手 (hasFz=false) は空き扱い (breed側で相手体形のみ寄与)
  for (int i = 0; i < 4; i++)
    g.fuse[i] = rtcPeers[best].hasFz ? rtcPeers[best].fz[i] : 255;
  return &g;
}

// 電波エントロピーでseedしたRNG (繁殖専用)。通常時はesp_random直結。
static uint32_t gSeed = 0x9E3779B9UL;
static uint32_t inkRand() {
  gSeed ^= gSeed << 13; gSeed ^= gSeed >> 17; gSeed ^= gSeed << 5;
  return gSeed;
}

// 世代交代。mate==nullptrで自家系＋変異。誕生EVENTを次無線で放送。
// 繁殖前にcore0で電波サーベイし、そのseedでRNGを初期化する (環境が遺伝に触る)。
void doRebirth(const genetics::Genes* mate) {
  // sv/saはstatic: jobs::runがタイムアウトで復帰してもcore0が触り続ける。
  // doRebirthは単発逐次呼び出し限定のため安全。FieldArg側はRTC常駐で元々安全。
  static radio::Survey sv;
  static jobs::SurveyArg sa{&sv, false};
  sa.allowBle = rtcAllowBle;
  if (jobs::run(jobs::SURVEY, &sa, 20000) && sv.seed) {
    gSeed = sv.seed;
    char rbuf[80];
    snprintf(rbuf, sizeof(rbuf), "+RADIO wifi=%u/%d ble=%u/%d %s seed=%X",
             (unsigned)sv.wifiN, (int)sv.wifiMax, (unsigned)sv.bleN, (int)sv.bleMax,
             sv.bleOk ? "ok" : "ng", (unsigned)gSeed);
    Serial.println(rbuf);
  } else {
    gSeed = esp_random();
    Serial.println("+RADIO fallback esp_random");
  }
  genetics::Genes A{rtcCre.intelligence, rtcCre.curiosity,
                    rtcCre.aggression, rtcCre.sociability, rtcCre.species_id,
                    {rtcCre.fuse[0], rtcCre.fuse[1], rtcCre.fuse[2], rtcCre.fuse[3]}};
  genetics::Genes B = mate ? *mate : A;
  genetics::Genes C = genetics::breed(A, B, inkRand);
  // 環境圧: 現象盤の対称性・活動量でvariantのみ微調整 (P0: morph保全。旧species直接加算は
  // bias±10でmorph(=species%12)がほぼ毎回ずれる事故があった。variant=species/12は将来の
  // 見た目差分 (P1) 領域。morphはbreed結果のまま固定する。
  {
    uint8_t sym = field::symmetry(rtcField);
    uint16_t act = field::activity(rtcField);
    int bias = (int)(sym * 3 / 101) * 7 + (act > 200 ? 2 : act > 80 ? 1 : 0) * 3 - 10;
    int morph = (int)C.species % 12;
    int variant = (int)C.species / 12;  // 0..83
    int nvar = (variant + bias) % 84;
    if (nvar < 0) nvar += 84;
    int nsp = nvar * 12 + morph;
    while (nsp >= 1000) nsp -= 12;  // 1000..1007域のみ。morph保全でvariantを1段下げる
    C.species = (uint16_t)nsp;
    char fldbuf[64];
    snprintf(fldbuf, sizeof(fldbuf), "+FIELD sym=%u act=%u bias=%d",
             (unsigned)sym, (unsigned)act, bias);
    Serial.println(fldbuf);
  }
  uint8_t ng = rtcCre.generation < 255 ? rtcCre.generation + 1 : 255;
  uint32_t did = rtcCre.device_id;
  char nm[16];
  strncpy(nm, rtcCre.name, sizeof(nm));
  rtcCre.health = 90; rtcCre.hunger = 20; rtcCre.energy = 90;
  rtcCre.happiness = 70; rtcCre.cleanliness = 80;
  rtcCre.intelligence = C.intelligence; rtcCre.curiosity = C.curiosity;
  rtcCre.aggression = C.aggression; rtcCre.sociability = C.sociability;
  rtcCre.species_id = C.species;
  rtcCre.generation = ng;
  for (int i = 0; i < 4; i++) rtcCre.fuse[i] = C.fuse[i];
  for (int i = 0; i < 3; i++) rtcCre.habit[i] = 0;  // 生まれたては万物が新鮮 (M10)
  rtcCre.device_id = did;
  strncpy(rtcCre.name, nm, sizeof(rtcCre.name));
  rtcCre.age_sec = 0;
  rtcCareGood = rtcCareMiss = rtcOverwork = 0;  // 新世代はお世話記録まっさら
  // 新世代では年齢がリセットされるため、知人帳のlastAgeもリセットしないとLRU置換が逆転する
  for (uint8_t i = 0; i < rtcPeerN; i++) rtcPeers[i].lastAge = 0;
  rtcCre.action = Action::IDLE;
  rtcCre.sleeping = false;
  rtcPendingEvt = 1;
  setEvent("BIRTH_OK");
  Serial.print("+BORN gen=");
  Serial.print(ng);
  Serial.print(" mate=");
  Serial.print(mate ? "peer" : "self");
  Serial.print(" tr=");
  Serial.print(C.intelligence); Serial.print(",");
  Serial.print(C.curiosity); Serial.print(",");
  Serial.print(C.aggression); Serial.print(",");
  Serial.print(C.sociability); Serial.print(" sp=");
  Serial.print(C.species); Serial.print(" fz=");
  Serial.print(C.fuse[0]); Serial.print(",");
  Serial.print(C.fuse[1]); Serial.print(",");
  Serial.print(C.fuse[2]); Serial.print(",");
  Serial.println(C.fuse[3]);
  store::save(rtcCre, rtcEvent, clk::rtcUs(), rtcUnix, rtcPendingEvt,
              rtcCareGood, rtcCareMiss, rtcOverwork);
}

void setEvent(const char* e) {
  strncpy(rtcEvent, e, sizeof(rtcEvent) - 1);
  rtcEvent[sizeof(rtcEvent) - 1] = 0;
  gEventSeq++;  // 描画要否判定用 (全イベントはここを通る)
  screen::pushLog(e, rtcCre.age_sec);
  Serial.print("+EVT ");
  Serial.println(rtcEvent);
}

// 実効昼夜。壁時計があればJST、なければ体内時計 (M10概日) にフォールバック。
inline bool effNight() {
  if (rtcUnix > 0) return clk::wallNightJST(rtcUnix);
  return creatureNight(rtcCre.age_sec);
}
inline bool effMorning() {
  if (rtcUnix > 0) return clk::wallMorningJST(rtcUnix);
  return false;  // 未同期時は朝ボーナスなし
}

// お世話カウンタ付き操作 (進化判定用。Creature本体は触らない)。
// 既存の setEvent(ui::feed/play/train(...)) 呼びは全てこちら経由にすること。
void careFeed() {
  const char* r = ui::feed(rtcCre);
  bool ok = strcmp(r, "FEED_OK") == 0;
  if (ok && rtcCareGood < 9999) rtcCareGood++;
  // 朝の挨拶ボーナス (壁時計5-8時・1日1回。happiness+10)
  if (ok && rtcUnix > 0) {
    uint32_t day = clk::wallDayJST(rtcUnix);
    if (clk::wallMorningJST(rtcUnix) && rtcOhayoDay != day) {
      rtcOhayoDay = day;
      rtcCre.happiness = min(100, (int)rtcCre.happiness + 10);
      setEvent("OHAYO");
      return;
    }
  }
  setEvent(r);
}
void carePlay() {
  const char* r = ui::play(rtcCre);
  if (strcmp(r, "PLAY_OK") == 0 && rtcCareGood < 9999) rtcCareGood++;
  setEvent(r);
}
void careTrain(int target = -1) {
  const char* r = ui::train(rtcCre, target);
  if (strcmp(r, "OVERWORK") == 0 && rtcOverwork < 9999) rtcOverwork++;
  setEvent(r);
}
void careClean() {
  const char* r = ui::clean(rtcCre);
  if (strcmp(r, "CLEAN_OK") == 0 && rtcCareGood < 9999) rtcCareGood++;
  setEvent(r);
}

// 反応速度検査 (SIDE長押し・手動訓練)。E-Inkは遅すぎて合図にならないため、
// カウントダウンとGOはLED+シリアルで出す (画面は開始と結果のみ)。
// 経済はTRAINダイスと同一 (コスト15en/12hu/5ha・過労ゲート・利得表)。腕の分だけ伸びる。
void runInspectGame() {
  static const char* TNAMES[] = {"INT", "AGGR", "CURIO", "SOC"};
  if (rtcCre.energy < 15) {  // 過労ゲート (TRAINと同一)
    rtcCre.health = (rtcCre.health > 5) ? rtcCre.health - 5 : 1;
    rtcCre.happiness = (rtcCre.happiness > 10) ? rtcCre.happiness - 10 : 0;
    rtcCre.action = Action::IDLE;
    if (rtcOverwork < 9999) rtcOverwork++;
    setEvent("OVERWORK");
    stayDraw(false);
    gStayTick = millis();
    return;
  }
  rtcCre.energy = (rtcCre.energy >= 15) ? rtcCre.energy - 15 : 0;
  rtcCre.hunger = min(100, (int)rtcCre.hunger + 12);
  rtcCre.happiness = (rtcCre.happiness >= 5) ? rtcCre.happiness - 5 : 0;
  uint8_t target = ui::pickTrainTarget(rtcCre);
  // 離し待ち (長押しの指が残っていても誤爆しない)。ボタン固着時は3秒で打ち切る:
  // 以降の進行はBOOTのみ参照 (GO判定・お手つき) のためSIDE保持のままでも必ず終局し、
  // FWが待ちループで永久に固まる事故を防ぐ (テレメトリ停止・PCから復旧不能になる)
  for (unsigned long rw = millis(); halLevel() && millis() - rw < 3000;) delay(10);
  setEvent("TEST_START");
  stayDraw(false);
  // カウントダウン3拍＋ランダム間隔。GO前のBOOT押下はお手つきとして記録する。
  unsigned long c0 = millis();
  uint32_t waitMs = 1800 + esp_random() % 1000;  // 数え合図防止
  uint8_t lastCount = 4;
  bool flying = false;
  while (millis() - c0 < waitMs) {
    unsigned long el = millis() - c0;
    if (el < 1800) {
      uint8_t count = (uint8_t)(3 - el / 600);  // 3,2,1
      if (count != lastCount) {
        lastCount = count;
        led::blip();
        Serial.print("+TEST ");
        Serial.println(count);
      }
    }
    if (halButtons() & 1) flying = true;
    delay(10);
  }
  led::blip();
  unsigned long t0 = millis();
  Serial.println("+TEST GO!!");
  // 応答窓2秒。BOOTのみ有効 (10msポーリングで±150ms判定に足る)。
  bool pressed = false;
  long dt = 0;
  while (millis() - t0 < 2000) {
    if (halButtons() & 1) { pressed = true; dt = (long)(millis() - t0); break; }
    delay(5);
  }
  uint8_t grade = flying ? 4 : ui::gradeInspect((int)dt, pressed);
  const char* ev = ui::applyInspect(rtcCre, target, grade);
  if (grade <= 2 && rtcCareGood < 9999) rtcCareGood++;
  Serial.print("+INSPECT target=");
  Serial.print(TNAMES[target]);
  Serial.print(" grade=");
  Serial.print(grade);
  Serial.print(" dt=");
  Serial.println(pressed ? dt : -1);
  setEvent(ev);
  if (grade == 0) {  // 王冠ファンファーレ (小物はパーシャルだと薄いのでfullで描く)
    led::blip(); delay(120); led::blip(); delay(120); led::blip();
  }
  stayDraw(grade == 0);
  gStayTick = millis();
}
// 飢餓放置の計上。30秒tick毎に呼ぶ (不在catch-up内も1step1回)。
inline void countNeglectTick() {
  if (rtcCre.hunger >= 95 && rtcCareMiss < 9999) rtcCareMiss++;
}
// 7200s跨ぎで進化判定。戻り値true=進化した (呼出側はfull描画すること)。
// 知人の好感度はその場で数える (aff>=50=BONDED、aff<=-50=RIVAL)。
bool maybeEvolve(uint32_t prevAge) {
  if (prevAge >= evo::LARVA_AGE_MAX || rtcCre.age_sec < evo::LARVA_AGE_MAX) return false;
  int bonded = 0, rival = 0;
  for (uint8_t i = 0; i < rtcPeerN; i++) {
    if (rtcPeers[i].aff >= 50) bonded++;
    else if (rtcPeers[i].aff <= -50) rival++;
  }
  int sc = evo::scoreOf(rtcCareGood, rtcCareMiss, rtcOverwork, bonded, rival);
  uint8_t rank = evo::rankOf(sc);
  uint8_t morph = evo::TABLE[rank][evo::domTrait(rtcCre)];
  uint8_t before = (uint8_t)(rtcCre.species_id % 12);
  evo::apply(rtcCre, morph);
  char buf[96];
  snprintf(buf, sizeof(buf), "+EVOLVE %u->%u rank=%c score=%d g=%u m=%u ow=%u bond=%d riv=%d",
           (unsigned)before, (unsigned)morph, "SABC"[rank], sc,
           (unsigned)rtcCareGood, (unsigned)rtcCareMiss, (unsigned)rtcOverwork,
           bonded, rival);
  Serial.println(buf);
  if (rtcPendingEvt == 0) rtcPendingEvt = 2;  // 進化報告を次無線で放送 (誕生が未送なら譲る)
  setEvent("EVOLVE");
  return true;
}

// 描画はここ経由。転送回数・残像の両面で節約する (E-Inkの電力・時間・寿命対策):
//  - backstop: dispHash一致→画素同一のため転送省略 (force/fullは無条件転送)
//  - cadence: 呼び出し側が通常tickを間引き (ROUTINE_DRAW_TICKS)。重要変化は即時
//  - 周期full: 12転送毎にfullで残像清掃 (partial連続のゴースト蓄積対策)
// 転送時は行動・気分・イベント世代・tick数をスナップし、loop側の要否判定に使う。
// ついでに転送時間を計測し、3秒超えはstall計上＋報告 (パネル失速の検出)。
void stayDraw(bool full, bool force) {
  uint32_t dh = screen::dispHash(rtcCre, rtcEvent, rtcPeerN);
  if (!full && !force && rtcHaveDrawn && dh == rtcLastDispHash) {
    gSkipCount++;  // 画素同一。パネルは既にこの内容を表示している
    return;
  }
  // 周期full (stay-awake路。sleep路はsetup側のboots周期で担うためここはRAM回数のみ)
  bool doFull = full || (gXferCount % PERIODIC_FULL_EVERY == 0);
  unsigned long t0 = micros();
  // 壁時計同期時は実効昼夜を表示 (未同期-1は体内時計表示)。
  // 季節帽子は期間のみ (壁時計必須。0=なし 1=かぼちゃ 2=サンタ 3=鏡餅)。
  int wn = rtcUnix > 0 ? (effNight() ? 1 : 0) : -1;
  uint8_t hk = rtcUnix > 0 ? clk::hatKindJST(rtcUnix) : 0;
  if (gDispOk) screen::draw(rtcCre, rtcEvent, doFull, rtcPeerN, &rtcField, wn, hk);
  unsigned long dt = micros() - t0;
  gDrawCount++;
  gXferCount++;
  if (doFull) gFullCount++;
  if (gDispOk && dt > 3000000UL) {
    gStallCount++;
    Serial.print("+STALL dt=");
    Serial.println(dt);
  }
  gLastDrawMs = millis();
  rtcLastDispHash = dh; rtcHaveDrawn = true;
  gDrawnAction = rtcCre.action; gDrawnMood = creatureMood(rtcCre);
  gDrawnEventSeq = gEventSeq; gTicksSinceDraw = 0;
}

// 描画内容hash (PX監査用)。vitals＋年齢＋行動＋イベント＋現象＋知人数。
// hashが変わったのに画面が変わらない→パネル転送側。hash不変→内容同一描画。
static uint32_t stateHash() {
  uint32_t h = 2166136261UL;
  auto mix = [&](uint32_t v) { h = (h ^ v) * 16777619UL; };
  mix(rtcCre.health); mix(rtcCre.hunger); mix(rtcCre.energy); mix(rtcCre.happiness);
  mix(rtcCre.cleanliness); mix(rtcCre.age_sec); mix((uint32_t)rtcCre.action);
  for (const char* p = rtcEvent; *p; p++) mix((uint32_t)(uint8_t)*p);
  mix(field::hash(rtcField)); mix(rtcPeerN);
  return h;
}

// 知人帳に記録。戻り値true=新規 (満杯時は最古を置換)。
bool learnPeer(const mesh::Peer& p) {
  if (p.did == rtcCre.device_id) return false;  // 自機パケットは登録しない
  for (uint8_t i = 0; i < rtcPeerN; i++) {
    if (rtcPeers[i].did == p.did) {
      rtcPeers[i].rssi = (int8_t)p.rssi;
      rtcPeers[i].lastAge = rtcCre.age_sec;
      if (rtcPeers[i].count < 255) rtcPeers[i].count++;
      if (p.type == mesh::T_HELLO) {  // 名刺更新 (転生後の形態変わり対応)
        rtcPeers[i].species = p.species;
        rtcPeers[i].gen = p.gen;
        rtcPeers[i].hasSpecies = true;
      }
      if (p.hasTr) {
        rtcPeers[i].ti = p.ti; rtcPeers[i].cu = p.cu;
        rtcPeers[i].ag = p.ag; rtcPeers[i].so = p.so;
        rtcPeers[i].hasTr = true;
      }
      // v1/v2旧FW (hasFz=false) では上書きせず既知fuseを保持する
      if (p.hasFz) {
        for (int k = 0; k < 4; k++) rtcPeers[i].fz[k] = p.fz[k];
        rtcPeers[i].hasFz = true;
      }
      return false;
    }
  }
  // 集約初期化はメンバ追加時の順序事故を招くため、代入式で構築する
  PeerInfo np{};
  np.did = p.did; np.lastAge = rtcCre.age_sec;
  np.species = p.species; np.gen = p.gen;
  np.rssi = (int8_t)p.rssi; np.count = 1;
  np.ti = p.ti; np.cu = p.cu; np.ag = p.ag; np.so = p.so;
  np.hasTr = p.hasTr; np.hasSpecies = (p.type == mesh::T_HELLO); np.aff = 0;
  for (int k = 0; k < 4; k++) np.fz[k] = p.hasFz ? p.fz[k] : 255;
  np.hasFz = p.hasFz;
  if (rtcPeerN < 6) {
    rtcPeers[rtcPeerN++] = np;
  } else {
    uint8_t old = 0;
    for (uint8_t i = 1; i < 6; i++)
      if (rtcPeers[i].lastAge < rtcPeers[old].lastAge) old = i;
    rtcPeers[old] = np;
  }
  Serial.print("+PEERS n=");
  Serial.println(rtcPeerN);
  return true;
}

// 知人の好感度参照。未登録は0 (初対面は無関心)。
static int8_t peerAff(uint32_t did) {
  for (uint8_t i = 0; i < rtcPeerN; i++)
    if (rtcPeers[i].did == did) return rtcPeers[i].aff;
  return 0;
}
// 好感度加算 (±100飽和)。±50 crossingでBONDED/RIVAL。未登録なら何もしない。
void addAff(uint32_t did, int d) {
  for (uint8_t i = 0; i < rtcPeerN; i++) {
    if (rtcPeers[i].did != did) continue;
    int before = rtcPeers[i].aff;
    int after = before + d;
    if (after > 100) after = 100;
    if (after < -100) after = -100;
    rtcPeers[i].aff = (int8_t)after;
    // 同一イベント連打のチャタリング防止 (decayAffとの往復でBONDED連発するため)。
    if (before < 50 && after >= 50) { if (strcmp(rtcEvent, "BONDED") != 0) setEvent("BONDED"); }
    else if (before > -50 && after <= -50) { if (strcmp(rtcEvent, "RIVAL") != 0) setEvent("RIVAL"); }
    return;
  }
}
// 飽き加算 (100飽和)。刺激の種類は habit[0]=FOOD 1=PLAY 2=SOCIAL。
static void bumpHabit(uint8_t idx, uint8_t d) {
  rtcCre.habit[idx] = rtcCre.habit[idx] > 100 - d ? 100 : rtcCre.habit[idx] + d;
}
// 好感度の自然減衰 (tick毎に0へ1)。6件走査の激安。長い不在は関係を冷ます。
void decayAff() {
  for (uint8_t i = 0; i < rtcPeerN; i++) {
    if (rtcPeers[i].aff > 0) rtcPeers[i].aff--;
    else if (rtcPeers[i].aff < 0) rtcPeers[i].aff++;
  }
}
// 既知かつ種既知の知人の系統を引く。STATUSのみ知人・未知はfalse (系統判定不能)。
// GREETING/FIGHTパケット自体にspeciesが無いため必須 (無ければ常にfamily 0扱いになる)。
static bool peerFamily(uint32_t did, uint8_t& fam) {
  for (uint8_t i = 0; i < rtcPeerN; i++)
    if (rtcPeers[i].did == did) {
      if (!rtcPeers[i].hasSpecies) return false;
      fam = genetics::familyOf(rtcPeers[i].species);
      return true;
    }
  return false;
}

// 受信リアクション (M7)。自動返信はしない (GREETING往復ループ防止)。
// 効果は自個体内の変化＋イベント表示のみ。
void reactPeer(const mesh::Peer& p) {
  if (p.did == rtcCre.device_id) return;  // 自機パケットには反応しない
  switch (p.type) {
    case mesh::T_GREETING: {
      // 効き = (同族5/他族3/未知4 ＋ 好感度/25) × 社交飽き。仲良しほど嬉しい。
      uint8_t pf = 0;
      bool known = peerFamily(p.did, pf);
      int8_t fa = peerAff(p.did);
      int tot;
      const char* ev;
      int affD;
      if (known && pf == genetics::familyOf(rtcCre.species_id)) {
        tot = 5 + fa / 25; ev = "ALLY_RX"; affD = 6;
      } else if (known) {
        tot = 3 + fa / 25; ev = "GREET_RX"; affD = 4;
      } else {
        tot = 4; ev = "STRANGER_RX"; affD = 2;  // 種未知のよそ者。好奇心だけ刺激
      }
      tot = habGain(tot, rtcCre.habit[2]);
      if (tot < 0) tot = 0;
      if (tot > 10) tot = 10;
      rtcCre.happiness = min(100, (int)rtcCre.happiness + tot);
      setEvent(ev);
      addAff(p.did, affD);
      bumpHabit(2, 20);
      break;
    }
    case mesh::T_FOOD:
      rtcCre.hunger = rtcCre.hunger > p.x1 ? rtcCre.hunger - p.x1 : 0;  // 栄養は飽きない
      rtcCre.happiness = min(100, (int)rtcCre.happiness + habGain(5, rtcCre.habit[0]));
      setEvent("FOOD_RX");
      addAff(p.did, 6);
      bumpHabit(0, 25);
      break;
    case mesh::T_PLAY:
      if (rtcCre.energy >= 20) {
        rtcCre.happiness = min(100, (int)rtcCre.happiness + habGain(8, rtcCre.habit[1]));
        rtcCre.energy -= 5;
        setEvent("PLAY_RX");
        addAff(p.did, 8);
        bumpHabit(1, 25);
      } else {
        setEvent("FATIGUE");
      }
      break;
    case mesh::T_FIGHT: {
      // 勝敗 = aggression＋乱数＋系統相性。荒事は命懸け。種未知の相手には相性なし (五分)。
      // 親友 (aff≥30) とは手加減試合: 痛み半減。いじめ (勝利) は好感度を失う。
      // バランス調整 (tools/balance_sim.pyで検証): 振れ幅30->40で番狂わせを残し、
      // 系統ボーナス+15->+8 (旧は互角でも優位側88%勝率の必勝級だった)。
      uint32_t mine = rtcCre.aggression + esp_random() % 40;
      uint32_t theirs = p.x1 + esp_random() % 40;
      uint8_t pf = 0;
      if (peerFamily(p.did, pf) &&
          genetics::familyBeats(genetics::familyOf(rtcCre.species_id), pf)) mine += 8;
      int8_t fa = peerAff(p.did);
      if (mine >= theirs) {
        rtcCre.happiness = min(100, (int)rtcCre.happiness + 10);
        setEvent("COMBAT_WIN");
        addAff(p.did, -5);
      } else {
        // 敗北: 痛みは親友の手加減 (aff≥30かつHPに余裕で2、それ以外は5)。
        // 下限1で踏み止まる (死はtickの衰弱に一任。旧if(health>dmg)は低HPで無傷になるバグ)。
        int dmg = (fa >= 30 && rtcCre.health > 2) ? 2 : 5;
        rtcCre.health = (rtcCre.health > dmg) ? rtcCre.health - dmg : 1;
        setEvent("COMBAT_LOSS");
        addAff(p.did, -10);
      }
      break;
    }
    case mesh::T_TRADE:
      // 交換提案 (give=X)。空腹なら受諾。親友 (aff>40) には少し空腹でも分ける。
      if (rtcCre.hunger > 40 || (peerAff(p.did) > 40 && rtcCre.hunger > 20)) {
        rtcCre.hunger = rtcCre.hunger > p.x1 ? rtcCre.hunger - p.x1 : 0;
        rtcCre.happiness = min(100, (int)rtcCre.happiness + habGain(5, rtcCre.habit[0]));
        setEvent("TRADE_OK");
        addAff(p.did, 6);
        bumpHabit(0, 25);
      } else {
        setEvent("TRADE_REFUSE");
        addAff(p.did, -2);
      }
      break;
    case mesh::T_EVENT:
      if (p.x1 == 1) {
        setEvent("BIRTH_RX"); rtcCre.happiness = min(100, (int)rtcCre.happiness + 5);
        addAff(p.did, 4);  // 誕生の祝いは絆になる
      }
      else if (p.x1 == 2) {
        setEvent("EVOLVE_RX"); rtcCre.happiness = min(100, (int)rtcCre.happiness + 5);
        addAff(p.did, 4);  // 進化の祝いも絆になる
      }
      else if (p.x1 == 3) {
        setEvent("GETWELL_RX"); rtcCre.happiness = min(100, (int)rtcCre.happiness + 3);
        addAff(p.did, 2);
      }
      else if (p.x1 == 4) { setEvent("SLEEP_RX"); addAff(p.did, 1); }
      break;
    default:
      break;  // HELLO/STATUSは知人帳のみ
  }
}

static const char* typeName(uint8_t t) {
  switch (t) {
    case mesh::T_HELLO: return "HELLO";
    case mesh::T_STATUS: return "STATUS";
    case mesh::T_GREETING: return "GREETING";
    case mesh::T_FOOD: return "FOOD";
    case mesh::T_PLAY: return "PLAY";
    case mesh::T_FIGHT: return "FIGHT";
    case mesh::T_TRADE: return "TRADE";
    case mesh::T_EVENT: return "EVENT";
  }
  return "?";
}

// 無線 cycle (HELLO+STATUS送信→行動パケット→誕生EVENT→2秒受信窓→sleep)。
void doRadioCycle() {
  SPI.begin(HAL_LORA_SCK, HAL_LORA_MISO, HAL_LORA_MOSI, HAL_LORA_NSS);
  if (!mesh::begin()) {
    Serial.println("+HELLO ng");
    return;
  }
  led::blip();  // 無線活動中は点灯 (tick停止中も光り続ける)
  Serial.println(mesh::sendHello(rtcCre) ? "+HELLO ok" : "+HELLO fail");
  Serial.println(mesh::sendStatus(rtcCre) ? "+STATUS tx ok" : "+STATUS tx fail");
  // 行動連動の1発 (M7)。COMM=挨拶、PLAY=誘い、FIGHT=挑戦、飢餓=物乞い。
  if (rtcCre.action == Action::COMM)
    Serial.println(mesh::sendGreeting(rtcCre) ? "+GREETING ok" : "+GREETING fail");
  else if (rtcCre.action == Action::PLAY && rtcPeerN > 0)
    Serial.println(mesh::sendPlay(rtcCre) ? "+PLAY tx ok" : "+PLAY tx fail");
  else if (rtcCre.action == Action::FIGHT)
    Serial.println(mesh::sendFight(rtcCre) ? "+FIGHT tx ok" : "+FIGHT tx fail");
  else if (rtcCre.hunger > 80 && rtcPeerN > 0)
    Serial.println(mesh::sendTrade(rtcCre, 0, 20) ? "+TRADE beg ok" : "+TRADE beg fail");
  if (rtcPendingEvt) {
    Serial.println(mesh::sendEvent(rtcCre, rtcPendingEvt) ? "+EVENT tx ok" : "+EVENT tx fail");
    rtcPendingEvt = 0;
  }
  mesh::Peer p;
  uint8_t radioBtn = 0;
  if (mesh::recvWindow(p, 2000, &radioBtn)) {
    if (p.did != rtcCre.device_id) {
      Serial.print("+HEARD did=");
      Serial.print(p.did, HEX);
      Serial.print(" type=");
      Serial.print(typeName(p.type));
      Serial.print(" rssi=");
      Serial.println(p.rssi, 1);
      bool isNew = learnPeer(p);
      reactPeer(p);
      if (isNew) setEvent("PEER_FOUND");
    } else {
      Serial.println("+HEARD self ignored");
    }
  } else if (radioBtn) {
    gPendBtn |= radioBtn;  // 受信窓中の押下はloop先頭で処理 (取りこぼし防止)
    Serial.println("+HEARD abort");
  } else {
    Serial.println("+HEARD none");
  }
  mesh::sleep();
}

// "TIME 1234567890" 行だけ拾う (起動窓用)。戻り値はunix秒、無ければ0。
// "STAY" 行で常時起動モードに入る (deep sleep回避)。
uint32_t pollTime(uint32_t window_ms, bool* btnPressed = nullptr) {
  static char buf[65];  // cyd式: 行バッファは固定配列。Stringのheap確保をしない
  static uint8_t blen = 0;
  static bool bOverflow = false;
  buf[blen] = 0;
  unsigned long t0 = millis();
  while (millis() - t0 < window_ms) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n') {
        uint32_t ret = 0;
        if (!bOverflow) {
          // 前後空白を飛ばして判定 (旧String::trim相当)
          char* p = buf;
          while (*p == ' ' || *p == '\t') p++;
          char* e = p + strlen(p);
          while (e > p && (e[-1] == ' ' || e[-1] == '\t')) *--e = 0;
          if (strncmp(p, "TIME ", 5) == 0) {
            // atolは巨大値で飽和/UBのためstrtoul＋範囲検査 (2038年問題は運用で許容)。
            char* ep = nullptr;
            unsigned long u = strtoul(p + 5, &ep, 10);
            if (ep != p + 5 && *ep == 0 && u > 1000000000UL && u <= 4294967295UL)
              ret = (uint32_t)u;
          } else if (strcmp(p, "STAY") == 0) {
            gStayAwake = true;
            Serial.println("+STAY nosleep");
          }
        }
        blen = 0; buf[0] = 0; bOverflow = false;
        if (ret) return ret;
      } else if (c != '\r') {
        if (!bOverflow) {
          if (blen < 64) { buf[blen++] = c; buf[blen] = 0; }
          else { bOverflow = true; blen = 0; buf[0] = 0; }
        }
      }
    }
    uint8_t b = halButtons();
    if (b) {
      if (btnPressed) *btnPressed = true;
      if (millis() > 8000) {  // 起動直後のUSB列挙ノイズ (BOOT誤爆) を無視。boot-hold判定は別路のため無影響
        led::blip();
        if (b & 2) carePlay(); else careFeed();
      }
      if (btnPressed) return 0;
    }
    delay(10);
  }
  return 0;
}
}  // namespace

void setup() {
  Serial.setTxBufferSize(1024);  // FIELDBダンプ(420B)等のバースト出力あふれ防止
  Serial.setRxBufferSize(512);   // PCコンパニオン接続時のコマンドバースト取りこぼし防止
  Serial.begin(115200);
  Serial.setTxTimeoutMs(1);     // 1msに短縮 (0はESP32 core 3.x HWCDCのtriesアンダーフロー死バグ、10msは詰まり時の失速要因)
  delay(300);
  Serial.println("+INK start");
  halInit();
  jobs::init();  // core0ワーカー起動 (loopはcore1)
  if (digitalRead(HAL_BTN_SIDE) == LOW) {
    // SIDE押しながら起動＝常時起動モード (ケーブルレス開発用)
    gStayAwake = true;
    Serial.println("+STAY boot-hold");
  }
  if (!SLEEP_ENABLE && !gStayAwake) {
    // M6開発中はsleep OFFが既定。実運用 (SLEEP_ENABLE=true) で周回する。
    gStayAwake = true;
    Serial.println("+SLEEP off (stay default)");
  }

  bool fresh = (rtcMagic != RTC_MAGIC);
  bool isGenesis = false;  // NVSにも居ない完全新規 (スプラッシュ用)
  const char* src = "fresh";
  uint32_t absence = 0;
  bool unixSynced = false;  // 今回TIME同期で壁時計を得たか (二重加算防止用)
  // BLEキルスイッチ読込 (NVS)。無ければ許可既定。
  {
    Preferences bp;
    if (bp.begin("inklife", true)) {
      rtcAllowBle = bp.getUChar("ble", 1) != 0;
      bp.end();
    }
  }
  if (!rtcFieldInit) {
    // 現象盤の創世。初回のみ。
    field::randomize(rtcField, esp_random());
    rtcFieldInit = true;
  }
  // 現象をcore0で4ステップ進行 (電源断復帰後の不在分は別途catch-up済みの tick 扱い)
  // faはstatic必須 (jobs::runタイムアウト後もcore0が参照するためスタック禁止)。
  {
    static jobs::FieldArg fa{&rtcField, 4};
    if (jobs::run(jobs::FIELD, &fa, 5000)) {
      Serial.print("+FIELD hash=");
      Serial.print(field::hash(rtcField), HEX);
      Serial.print(" act=");
      Serial.print(field::activity(rtcField));
      Serial.print(" sym=");
      Serial.println(field::symmetry(rtcField));
    } else {
      Serial.println("+FIELD timeout");
    }
  }
  if (fresh) {
    rtcPeerN = 0;
    memset(rtcPeers, 0, sizeof(rtcPeers));
    uint64_t savedRtc = 0;
    uint32_t savedUnix = 0;
    char ev[32] = {0};
    uint8_t pev = 0;
    uint16_t cg = 0, cm = 0, ow = 0;
    if (store::load(rtcCre, ev, sizeof(ev), savedRtc, savedUnix, pev, cg, cm, ow)) {
      // 電源断復帰。TIMEを待って不在時間を確定させる (最大25秒、電池時は即諦め)。
      src = "nvs";
      strncpy(rtcEvent, ev, sizeof(rtcEvent) - 1);
      rtcPendingEvt = pev;  // 未送EVENT (誕生放送) を再起動越えで引継ぎ
      // 壁時計の復元 (TIMEが来なくても季節・昼夜が動くよう。前回保存値＋RTC経過)。
      // 電源断でRTCが死んでいたら経過0扱いで保存値のまま (TIME待ちで上書きされる)。
      if (savedUnix > 0) rtcUnix = savedUnix + clk::sleptSec(savedRtc, clk::rtcUs());
      Serial.println("+WAITTIME 25s (or press button to skip)");
      unsigned long t0 = millis();
      uint32_t unixNow = 0;
      while (millis() - t0 < 25000 && unixNow == 0) {
        bool skipBtn = false;
        unixNow = pollTime(200, &skipBtn);
        if (skipBtn) {
          Serial.println("+WAITTIME skip by button");
          break;
        }
      }
      if (unixNow > 0 && savedUnix > 0 && unixNow > savedUnix) {
        absence = unixNow - savedUnix;
        rtcUnix = unixNow;
        unixSynced = true;
        Serial.print("+ABSENCE ");
        Serial.print(absence);
        Serial.println("s");
      } else {
        setEvent("WAKE_OK");
      }
      rtcCareGood = cg; rtcCareMiss = cm; rtcOverwork = ow;  // お世話記録を電源断越えで引継ぎ
    } else {
      isGenesis = true;
      creatureInit(rtcCre);
      strncpy(rtcEvent, "GENESIS", sizeof(rtcEvent) - 1);
      rtcPendingEvt = 1;  // 誕生EVENTは次無線で放送
      rtcCareGood = rtcCareMiss = rtcOverwork = 0;  // 生まれたては記録なし
    }
    rtcMagic = RTC_MAGIC;
    rtcBoots = 0;
  } else if (power::wokeFromSleep()) {
    src = "rtc";
    absence = clk::sleptSec(rtcLastUs, clk::rtcUs());
  }
  rtcBoots++;
  Serial.print("+RESTORED src=");
  Serial.print(src);
  Serial.print(" absence=");
  Serial.print(absence);
  Serial.print(" boots=");
  Serial.println(rtcBoots);

  // 不在分を30秒刻みで適用。関係も冷ます。昼夜を跨いだら遷移イベント。
  // 不在中に7200sを跨いだら進化判定もここで (長期留守でも育ちは止めない)。
  // 壁時計は不在分だけ進める (TIME同期時は既に最新のため加算しない)。
  uint32_t ev0 = gEventSeq; Action act0 = rtcCre.action;  // 描画要否判定用スナップ
  bool nightBefore = effNight();
  if (!unixSynced && rtcUnix > 0 && absence > 0) rtcUnix += absence;
  uint32_t preAge = rtcCre.age_sec;
  uint32_t steps = absence / 30;
  if (steps > CATCHUP_MAX_STEPS) steps = CATCHUP_MAX_STEPS;
  for (uint32_t i = 0; i < steps; i++) { creatureTick(rtcCre, 30); decayAff(); countNeglectTick(); }
  bool justEvolved = maybeEvolve(preAge);
  if (effNight() != nightBefore)
    setEvent(effNight() ? "NIGHTFALL" : "DAYBREAK");

  Action na = ai::decide(rtcCre, rtcPeerN, effNight(), effMorning());
  if (!fresh && na != rtcCre.action) {
    rtcCre.action = na;
    const char* ev = actionEvent(na);
    if (ev[0]) setEvent(ev);
  }
  bool justReborn = false;
  if (rtcCre.health == 0) {  // 不在中の死もここで世代交代
    Serial.println("+DEAD");
    doRebirth(findMateGenes());
    justReborn = true;  // 新個体は残像なしのfullで迎える
  }
  if (!fresh && strcmp(power::wakeName(), "button") == 0) {
    careFeed();
  }

  gDispOk = screen::init();
  Serial.print("+INK disp ");
  Serial.println(gDispOk ? "ok" : "BUSY_STUCK");

  // 無線 (4周回に1回): HELLO+STATUS送信→2秒受信窓→sleep。常時受信はしない。
  if (rtcBoots % 4 == 0) doRadioCycle();
  if (isGenesis && gDispOk) {  // 初誕生のみスプラッシュ
    screen::splash(rtcCre);
    delay(2500);
  }
  // sleep復帰路の間引き: 初回・4周回毎・状態変化時のみ転送 (loop路と同一cadence)。
  // fullは初回・転生・16周回毎 (約8分毎の残像清掃。stay-awake路はstayDraw内の転送周期で担う)
  bool acted = fresh || (gEventSeq != ev0) || (rtcCre.action != act0);
  bool fullNow = fresh || justReborn || justEvolved || (rtcBoots % 16 == 0);
  if (gDispOk && (acted || rtcBoots % 4 == 0)) stayDraw(fullNow);
  logLife();

  // 就寝前の短窓: 通常1.5秒 (ボタン受付)
  unsigned long w0 = millis();
  while (millis() - w0 < 1500) {
    if (millis() - w0 > 800) {
      uint8_t b = halButtons();
      if (b && gDispOk) {
        led::blip();
        if ((b & 3) == 3) careClean();
        else if (b & 2) carePlay(); else careFeed();
        stayDraw(false);
      }
    }
    delay(50);
  }

  // NVS保存は4周回に1回 (フラッシュ消耗抑制)。電源断時は最大2分ロス。
  if (rtcBoots % 4 == 0) {
    bool ok = store::save(rtcCre, rtcEvent, clk::rtcUs(), rtcUnix, rtcPendingEvt,
                        rtcCareGood, rtcCareMiss, rtcOverwork);
    Serial.print("+SAVED ");
    Serial.println(ok ? "ok" : "FAIL");
  }
  if (gStayAwake) {
    Serial.println("+STAYAWAKE nosleep loop");
    gStayTick = millis();
    return;  // 睡眠せずloopへ (開発・PC接続用)
  }
  rtcLastUs = clk::rtcUs();
  if (gDispOk) screen::hibernate();  // パネルDC-DC昇圧回路等を完全休止して漏電防止
  power::sleepCycle(TICK_SEC);  // 戻らない
}

// FOODおすそわけ放送 (BOOT長押し用)。無線を都度起こして送って寝かせる。
void giftFood() {
  SPI.begin(HAL_LORA_SCK, HAL_LORA_MISO, HAL_LORA_MOSI, HAL_LORA_NSS);
  if (!mesh::begin()) {
    Serial.println("+FOOD ng");
    return;
  }
  Serial.println(mesh::sendFood(rtcCre, 20) ? "+FOOD tx ok" : "+FOOD tx fail");
  mesh::sleep();
  setEvent("FOOD_TX");
}

// 16進パケット行の解析 (INJECT用)。不正なら-1。
static int hexNybble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
static int hexParse(const char* s, uint8_t* out, int maxn) {
  int sl = strlen(s);
  if (sl == 0 || (sl & 1) || sl / 2 > maxn) return -1;
  for (int i = 0; i < sl; i += 2) {
    int hi = hexNybble(s[i]), lo = hexNybble(s[i + 1]);
    if (hi < 0 || lo < 0) return -1;
    out[i / 2] = (uint8_t)((hi << 4) | lo);
  }
  return sl / 2;
}

void loop() {
  if (!gStayAwake) return;  // 通常運用ではここに来ない
  // 常時起動モード: 30秒tick＋ボタン＋TIME受付。USB抜去まで眠らない。
  uint8_t b = halButtons() | gPendBtn;  // 受信窓中の押下も拾う
  gPendBtn = 0;
  // BOOT+SIDE同時押し＝掃除 (4ジェスチャ枯渇後の唯一の空き)。
  // エッジではなくレベルで見る (同時押しのタイミングずれ対策)。同時押し中は単押し・長押しに流さない。
  {
    static bool bothFired = false;
    if ((halLevel() & 3) == 3 && millis() > 8000) {  // pollTime側と同一ガード
      if (!bothFired) {
        bothFired = true;
        led::blip();
        careClean();
        stayDraw(false);
        gStayTick = millis();
      }
      b &= ~3;
    } else {
      bothFired = false;
    }
  }
  if (b && millis() > 8000) {  // pollTime側と同一ガード (USB列挙ノイズ対策)
    led::blip();
    Serial.print("+BTN b=");
    Serial.print(b);
    Serial.print(" t=");
    Serial.println(millis());
    if (b & 2) carePlay(); else careFeed();
    stayDraw(false);
    gStayTick = millis();
  }
  // BOOT長押し (1.2秒) でFOODおすそわけ
  {
    static unsigned long pressStart = 0;
    static bool fired = false;
    if (halLevel() & 1) {
      if (pressStart == 0) {
        pressStart = millis();
        fired = false;
      } else if (!fired && (halLevel() & 3) != 3 && millis() - pressStart > 1200) {
        fired = true;
        giftFood();
        stayDraw(false);
      }
    } else {
      pressStart = 0;
      fired = false;
    }
  }
  // SIDE長押し (1.2秒) でトレーニング (MF2式)
  {
    static unsigned long sidePressStart = 0;
    static bool sideFired = false;
    if (halLevel() & 2) {
      if (sidePressStart == 0) {
        sidePressStart = millis();
        sideFired = false;
      } else if (!sideFired && (halLevel() & 3) != 3 && millis() - sidePressStart > 1200) {
        sideFired = true;
        runInspectGame();  // SIDE長押し＝反応速度検査 (手動訓練。ダイス自動はTRAINコマンド側)
      }
    } else {
      sidePressStart = 0;
      sideFired = false;
    }
  }
  // TIME行の受付 (PC時刻同期用)。STARVE/REBORNは開発用デバッグ。
  // INJECT/KILL/AGE/FEED/SPLASHはシリアル疑似試験用 (対向機なしで全要素を試す)。
  static char tbuf[65];  // cyd式: 固定配列 (String不使用)
  static uint8_t tblen = 0;
  static bool tbOverflow = false;
  tbuf[tblen] = 0;
  int rxLimit = 0;
  while (Serial.available() && ++rxLimit < 256) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (!tbOverflow) {
        char* p = tbuf;
        while (*p == ' ' || *p == '\t') p++;
        char* e = p + strlen(p);
        while (e > p && (e[-1] == ' ' || e[-1] == '\t')) *--e = 0;
      if (strncmp(p, "TIME ", 5) == 0) {
        char* ep = nullptr;
        unsigned long u = strtoul(p + 5, &ep, 10);
        if (ep != p + 5 && *ep == 0 && u > 1000000000UL && u <= 4294967295UL) {
          rtcUnix = (uint32_t)u;
          Serial.println("+TIME ok");
        } else {
          Serial.println("+TIME ng");
        }
      } else if (strcmp(p, "STARVE") == 0) {
        rtcCre.hunger = 100;
        Serial.println("+STARVE ok");
      } else if (strcmp(p, "REBORN") == 0) {
        doRebirth(findMateGenes());
        stayDraw(true);
      } else if (strcmp(p, "BLE 0") == 0 || strcmp(p, "BLE 1") == 0) {
        // BLEスキャンのキルスイッチ (開発用)。不安定時のみ切る。
        rtcAllowBle = (p[4] == '1');
        Preferences bp;
        if (bp.begin("inklife", false)) {
          bp.putUChar("ble", rtcAllowBle ? 1 : 0);
          bp.end();
        }
        Serial.print("+BLE ");
        Serial.println(rtcAllowBle ? "on" : "off");
      } else if (strcmp(p, "BENCH") == 0) {
        // sprite描画CPU時間計測 (e-ink転送を除く純粋描画)。HexaMIDIのbench流儀
        unsigned long bt0 = micros();
        for (int i = 0; i < 20; i++) screen::sprite(rtcCre, creatureMood(rtcCre), 4, 16);
        Serial.print("+BENCH sprite20us=");
        Serial.println((unsigned long)(micros() - bt0));
        stayDraw(false, true);  // バッファ復旧＋表示確認 (診断のためskip無効)
      } else if (strncmp(p, "INJECT ", 7) == 0) {
        // 疑似受信: 16進パケットをparsePacket→react/learnへ。無線路と同一判定。
        uint8_t b[32];
        mesh::Peer peer;
        int n = hexParse(p + 7, b, sizeof(b));
        if (n > 0 && mesh::parsePacket(b, n, -50.0f, 7.0f, peer)) {
          Serial.print("+INJECT ok n=");
          Serial.println(n);
          if (peer.did != rtcCre.device_id) {
            Serial.print("+HEARD did=");
            Serial.print(peer.did, HEX);
            Serial.print(" type=");
            Serial.print(typeName(peer.type));
            Serial.println(" (sim)");
            bool isNew = learnPeer(peer);
            reactPeer(peer);
            if (isNew) setEvent("PEER_FOUND");
          } else {
            Serial.println("+HEARD self ignored");
          }
        } else {
          Serial.println("+INJECT ng");
        }
      } else if (strcmp(p, "KILL") == 0) {
        // 疑似死: 次tickで+DEAD→自動世代交代。regen封じに飢餓併発
        rtcCre.health = 0;
        rtcCre.hunger = 100;
        Serial.println("+KILL ok");
      } else if (strncmp(p, "AGE ", 4) == 0) {
        char* ep = nullptr;
        long a = strtol(p + 4, &ep, 10);
        if (ep != p + 4 && *ep == 0 && a >= 0 && a <= 500000) {
          rtcCre.age_sec = (uint32_t)a;
          Serial.println("+AGE ok");
        } else {
          Serial.println("+AGE ng");
        }
      } else if (strcmp(p, "FEED") == 0) {
        careFeed();
        stayDraw(false);  // E-Ink即時反映 (PC連れ回し対応)
        Serial.println("+FEED ok");
      } else if (strcmp(p, "PLAY") == 0) {
        // PC連れ回し用。SIDE短押しと同等 (energy gateあり)。
        carePlay();
        stayDraw(false);
        Serial.println("+PLAY ok");
      } else if (strcmp(p, "CLEAN") == 0) {
        careClean();
        stayDraw(false);
        Serial.println("+CLEAN ok");
      } else if (strcmp(p, "CURE") == 0) {
        // お薬はボタンに置かない (逼迫回避)。シリアル/PC専用。SICK圏外はNO_NEED。
        setEvent(ui::cure(rtcCre));
        stayDraw(false);
        Serial.println("+CURE ok");
      } else if (strncmp(p, "TRAIN", 5) == 0) {
        // MF2式トレーニング (TRAIN / TRAIN INT / TRAIN AGGR / TRAIN CURIO / TRAIN SOC)
        int target = -1;
        if (strstr(p, "INT")) target = 0;
        else if (strstr(p, "AGGR")) target = 1;
        else if (strstr(p, "CURIO")) target = 2;
        else if (strstr(p, "SOC")) target = 3;
        careTrain(target);
        stayDraw(false);
        Serial.println("+TRAIN ok");
      } else if (strncmp(p, "INSPECT ", 8) == 0) {
        // PC主催ゲームの結果適用 (PC側で計時、FWは経済処理のみ。将来のPCリアルタイム検査用)。
        // INSPECT <0:PERFECT..3:FAIL>。TRAINと同一コスト・過労ゲート。
        int g = -1;
        if (sscanf(p + 8, "%d", &g) == 1 && g >= 0 && g <= 3) {
          if (rtcCre.energy < 15) {
            rtcCre.health = (rtcCre.health > 5) ? rtcCre.health - 5 : 1;
            rtcCre.happiness = (rtcCre.happiness > 10) ? rtcCre.happiness - 10 : 0;
            rtcCre.action = Action::IDLE;
            if (rtcOverwork < 9999) rtcOverwork++;
            setEvent("OVERWORK");
          } else {
            rtcCre.energy = (rtcCre.energy >= 15) ? rtcCre.energy - 15 : 0;
            rtcCre.hunger = min(100, (int)rtcCre.hunger + 12);
            rtcCre.happiness = (rtcCre.happiness >= 5) ? rtcCre.happiness - 5 : 0;
            uint8_t target = ui::pickTrainTarget(rtcCre);
            const char* ev = ui::applyInspect(rtcCre, target, (uint8_t)g);
            if (g <= 2 && rtcCareGood < 9999) rtcCareGood++;  // 実機SIDE長押し路と同じ (FAIL/FLYINGは加点なし)
            setEvent(ev);
          }
          stayDraw(g == 0);  // PERFECTの王冠はfullで描く (パーシャルだと薄い)
          Serial.println("+INSPECT ok");
        } else {
          Serial.println("+INSPECT ng");
        }
      } else if (strncmp(p, "TOURNEY ", 8) == 0) {
        // PCトーナメント終了時の疲労フィードバック (TOURNEY <energy_loss> <hunger_gain> <win:0|1>)
        // 不正・負値・範囲外は破棄 (旧sscanf無検査はuint8_tラップでvitals破壊)。
        int el = 0, hg = 0, win = 0;
        if (sscanf(p + 8, "%d %d %d", &el, &hg, &win) == 3 &&
            el >= 0 && el <= 100 && hg >= 0 && hg <= 100 && (win == 0 || win == 1)) {
          rtcCre.energy = (uint8_t)max(0, (int)rtcCre.energy - el);
          rtcCre.hunger = (uint8_t)min(100, (int)rtcCre.hunger + hg);
          if (win) rtcCre.happiness = (uint8_t)min(100, (int)rtcCre.happiness + 10);
          setEvent("FATIGUE");  // 既存の疲労演出・低エネルギーSLEEPY遷移を流用
          stayDraw(false);
          Serial.println(win ? "+TOURNEY ack win" : "+TOURNEY ack lose");
        } else {
          Serial.println("+TOURNEY ng");
        }
      } else if (strcmp(p, "FZ") == 0) {
        // 融合遺伝子照会 (PC連れ回し用)。+FZ a,b,c,d (255=空き)
        Serial.print("+FZ ");
        Serial.print(rtcCre.fuse[0]); Serial.print(",");
        Serial.print(rtcCre.fuse[1]); Serial.print(",");
        Serial.print(rtcCre.fuse[2]); Serial.print(",");
        Serial.println(rtcCre.fuse[3]);
      } else if (strcmp(p, "SP") == 0) {
        // 種番号照会 (PC連れ回し用)。+SP 123
        Serial.print("+SP ");
        Serial.println(rtcCre.species_id);
      } else if (strcmp(p, "ID") == 0) {
        // 個体ID照会 (PCのID表示同期用)。+ID <HEX8>
        Serial.print("+ID ");
        Serial.println(rtcCre.device_id, HEX);
      } else if (strcmp(p, "AFF") == 0) {
        // 好感度・飽きのぞき見 (M10試験用)。+AFF n / +AFF did aff / +AFF habit
        char abuf[80];
        snprintf(abuf, sizeof(abuf), "+AFF n=%u", (unsigned)rtcPeerN);
        Serial.println(abuf);
        for (uint8_t i = 0; i < rtcPeerN; i++) {
          if (rtcPeers[i].hasFz) {
            snprintf(abuf, sizeof(abuf), "+AFF %X aff=%d %s fz=%u,%u,%u,%u",
                     (unsigned)rtcPeers[i].did, (int)rtcPeers[i].aff,
                     rtcPeers[i].hasSpecies ? "known" : "strange",
                     (unsigned)rtcPeers[i].fz[0], (unsigned)rtcPeers[i].fz[1],
                     (unsigned)rtcPeers[i].fz[2], (unsigned)rtcPeers[i].fz[3]);
          } else {
            snprintf(abuf, sizeof(abuf), "+AFF %X aff=%d %s fz=-",
                     (unsigned)rtcPeers[i].did, (int)rtcPeers[i].aff,
                     rtcPeers[i].hasSpecies ? "known" : "strange");
          }
          Serial.println(abuf);
        }
        snprintf(abuf, sizeof(abuf), "+AFF habit=%u,%u,%u",
                 (unsigned)rtcCre.habit[0], (unsigned)rtcCre.habit[1], (unsigned)rtcCre.habit[2]);
        Serial.println(abuf);
      } else if (strcmp(p, "CARE") == 0) {
        // お世話カウンタのぞき見 (進化判定の内訳そのまま)。+CARE g=.. m=.. ow=.. bond=.. riv=.. score=.. rank=X
        int bonded = 0, rival = 0;
        for (uint8_t i = 0; i < rtcPeerN; i++) {
          if (rtcPeers[i].aff >= 50) bonded++;
          else if (rtcPeers[i].aff <= -50) rival++;
        }
        int sc = evo::scoreOf(rtcCareGood, rtcCareMiss, rtcOverwork, bonded, rival);
        char cbuf[112];
        snprintf(cbuf, sizeof(cbuf), "+CARE g=%u m=%u ow=%u cl=%u bond=%d riv=%d score=%d rank=%c w=%u hat=%u",
                 (unsigned)rtcCareGood, (unsigned)rtcCareMiss, (unsigned)rtcOverwork,
                 (unsigned)rtcCre.cleanliness,
                 bonded, rival, sc, "SABC"[evo::rankOf(sc)],
                 (unsigned)rtcUnix, rtcUnix > 0 ? clk::hatKindJST(rtcUnix) : 0);
        Serial.println(cbuf);
      } else if (strcmp(p, "PX") == 0) {
        // 更新監査: 内容hash＋表示hash＋描画/省略/full回数＋転送通番＋失速数＋最終描画からの経過ms
        char pbuf[140];
        snprintf(pbuf, sizeof(pbuf), "+PX hash=%X dh=%X draws=%u skips=%u fulls=%u xfer=%u stalls=%u ago=%lu",
                 (unsigned)stateHash(), (unsigned)screen::dispHash(rtcCre, rtcEvent, rtcPeerN),
                 (unsigned)gDrawCount, (unsigned)gSkipCount, (unsigned)gFullCount,
                 (unsigned)gXferCount, (unsigned)gStallCount, (unsigned long)(millis() - gLastDrawMs));
        Serial.println(pbuf);
      } else if (strcmp(p, "FIELDB") == 0) {
        // 現象盤ダンプ (PC連れ回し用)。12行 +FIELDB <row> <24hex> (2bit/cell packing)
        char fbuf[40];
        for (uint8_t fy = 0; fy < field::H; fy++) {
          int pos = snprintf(fbuf, sizeof(fbuf), "+FIELDB %u ", (unsigned)fy);
          for (uint8_t fx = 0; fx < field::W; fx += 4) {
            uint8_t b = 0;
            for (uint8_t k = 0; k < 4; k++) b |= (field::get(rtcField, fx + k, fy) & 3) << (k * 2);
            pos += snprintf(fbuf + pos, sizeof(fbuf) - pos, "%02X", b);
          }
          Serial.println(fbuf);
        }
      } else if (strcmp(p, "SPLASH") == 0) {
          if (gDispOk) {
            screen::splash(rtcCre);
            delay(2500);
            screen::draw(rtcCre, rtcEvent, true, rtcPeerN, &rtcField);
          }
          Serial.println("+SPLASH ok");
        }
      }
      tblen = 0; tbuf[0] = 0; tbOverflow = false;
    } else if (c != '\r') {
      if (!tbOverflow) {
        if (tblen < 64) { tbuf[tblen++] = c; tbuf[tblen] = 0; }
        else { tbOverflow = true; tblen = 0; tbuf[0] = 0; }
      }
    }
  }
  if (millis() - gStayTick >= TICK_SEC * 1000UL) {
    gStayTick = millis();
    bool nightBefore = effNight();
    uint32_t preAge = rtcCre.age_sec;
    creatureTick(rtcCre, TICK_SEC);
    decayAff();
    countNeglectTick();
    if (rtcUnix > 0) rtcUnix += TICK_SEC;  // 壁時計の進行 (未同期0のままなら体内時計)
    if (effNight() != nightBefore)
      setEvent(effNight() ? "NIGHTFALL" : "DAYBREAK");
    {
      // 現象進行はcore0 (数msのはず。詰まったら諦めて次へ)
      // faはstatic必須 (タイムアウト後にcore0が触るためスタック禁止)。
      static jobs::FieldArg fa{&rtcField, 4};
      jobs::run(jobs::FIELD, &fa, 5000);
    }
    bool reborn = false;
    if (rtcCre.health == 0) {
      // 寿命。知人の遺伝子があれば交配、なければ自家系で次世代へ。
      Serial.println("+DEAD");
      doRebirth(findMateGenes());
      stayDraw(true);
      reborn = true;
    }
    bool evolved = false;
    if (!reborn) {
      // 7200s跨ぎで進化。転生と同様に残像なしのfullで迎える。
      if (maybeEvolve(preAge)) {
        stayDraw(true);
        evolved = true;
      } else {
        Action na = ai::decide(rtcCre, rtcPeerN, effNight(), effMorning());
        if (na != rtcCre.action) {
          rtcCre.action = na;
          const char* ev = actionEvent(na);
          if (ev[0]) setEvent(ev);
        }
      }
    }
    logLife();
    gTicksSinceDraw++;
    // 通常tickはROUTINE_DRAW_TICKS毎 (約2分毎) のみ転送。行動・気分・イベント変化は即時。
    // 転生・進化直後は描き済みのため間引く。
    if (!reborn && !evolved) {
      bool urgent = (rtcCre.action != gDrawnAction) ||
                    (creatureMood(rtcCre) != gDrawnMood) ||
                    (gEventSeq != gDrawnEventSeq);
      if ((millis() - gLastDrawMs > 2000) &&  // 直後に描いたばかりなら重複抑制
          (urgent || gTicksSinceDraw >= ROUTINE_DRAW_TICKS)) stayDraw(false);
    }
    rtcBoots++;
    if (rtcBoots % 8 == 0) {  // 約4分に1回保存
      Serial.print("+SAVED ");
      Serial.println(store::save(rtcCre, rtcEvent, clk::rtcUs(), rtcUnix, rtcPendingEvt,
                                 rtcCareGood, rtcCareMiss, rtcOverwork) ? "ok" : "FAIL");
    }
    if (rtcBoots % 4 == 0) doRadioCycle();  // sleep路と同じcadence
  }
  led::tick(rtcCre.energy, rtcCre.sleeping, rtcCre.health < 30);
  delay(50);
}
