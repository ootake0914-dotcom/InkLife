#!/usr/bin/env python3
"""tools/balance_sim.py — InkLife 実機ロジックの忠実Python再現＋バランススイープ.

再現元 (FW正):
- src/life/creature.h … creatureTick / creatureMood / habGain / creatureNight
- src/behavior/ai.h … Utility AI scorers + decide (hysteresis +10)
- src/ui/actions.h … feed / play / train (MF2式ダイス、整数演算まで再現)
- src/genetics/breeding.h … breed / mutate / zoneOf / familyBeats
- InkLife.ino … reactPeer(T_FIGHT/GREETING/FOOD/PLAY/TRADE)、addAff/decayAff、TOURNEY

C++整数除算の切り捨て (負数は0方向) まで合わせている。乱数は FW の esp_random()%n
相当の一様整数で、seed指定で再現可能。

使い方:
  python tools/balance_sim.py train-dist [--seed 1]
  python tools/balance_sim.py grind [--sessions 200 --seed 1]
  python tools/balance_sim.py fight [--trials 20000 --seed 1]
  python tools/balance_sim.py life [--days 3 --seed 1]
  python tools/balance_sim.py all
"""
from __future__ import annotations
import argparse
import random
import sys

# --------------------------------------------------------------------------
# 定数 (FWと1:1対応。調整時はここを変える)
# --------------------------------------------------------------------------
APTITUDE = [  # src/ui/actions.h MORPH_TRAIT_APTITUDE
    (0, 3), (1, 2), (3, 0), (1, 2),
    (2, 1), (0, 2), (2, 3), (3, 0),
    (0, 3), (1, 0), (0, 2), (3, 2),
]
TRAIT_NAMES = ["INT", "AGGR", "CURIO", "SOC"]

TRAIN_ENERGY_COST = 15  # FW actions.h と同期 (旧18)
TRAIN_HUNGER_COST = 12
TRAIN_HAPPINESS_COST = 5
TRAIN_OVERWORK_EN = 15
TRAIN_AUTO_P = 70  # 適性70%:最得意 / 30%:第2適性
TRAIN_GREAT_HIGH = 20  # ha>=70 and en>=50
TRAIN_GREAT_LOW = 6
TRAIN_GREAT_BASE = 4  # GREAT gain 4〜5 (FWと同期。旧3)
TRAIN_SUCCESS_BASE = 2  # SUCCESS gain 2〜3 (FWと同期。旧1)

FIGHT_RAND = 40      # FW InkLife.ino と同期 (旧30)
FIGHT_FAMILY_BONUS = 8  # FWと同期 (旧15)
FIGHT_WIN_TIE = True  # mine >= theirs で勝ち

TICK_HUNGER_UP = 2
TICK_ENERGY_DOWN = 2
TICK_SLEEP_RECOVER_DAY = 10
TICK_SLEEP_RECOVER_NIGHT = 12
TICK_PLAY_HAPPY_UP = 8
TICK_PLAY_ENERGY_DOWN = 4
TICK_EAT_HUNGER_DOWN = 12
OLD_AGE_SEC = 259200  # 3日

AFF_MIN, AFF_MAX = -100, 100


def cxx_div(a: int, b: int) -> int:
    """C++ の整数除算 (0方向切り捨て)。fa/25 の負数対策に必須。"""
    return int(a / b)


def hab_gain(base: int, exposure: int) -> int:
    m = 100 - exposure
    if m < 20:
        m = 20
    return (base * m + 50) // 100


def creature_night(age_sec: int) -> bool:
    return (age_sec % 86400) >= 57600


class Creature:
    def __init__(self, did: int = 0xABCD1234, species: int = 250, gen: int = 1,
                 hp: int = 90, hu: int = 20, en: int = 90, ha: int = 70, cl: int = 80,
                 tr: tuple = (50, 50, 30, 40), age: int = 0, action: str = "IDLE"):
        self.did = did
        self.species = species
        self.gen = gen
        self.hp, self.hu, self.en, self.ha, self.cl = hp, hu, en, ha, cl
        self.in_, self.cu, self.ag, self.so = tr
        self.age = age
        self.action = action  # IDLE/SLEEP/EAT/PLAY/EXPLORE/COMM/...
        self.sleeping = False
        self.fuse = [255, 255, 255, 255]
        self.habit = [0, 0, 0]

    def copy(self) -> "Creature":
        c = Creature()
        c.__dict__.update({k: (list(v) if isinstance(v, list) else v)
                           for k, v in self.__dict__.items()})
        return c


def creature_mood(c: Creature) -> str:
    if c.hp < 30:
        return "SICK"
    if c.sleeping or c.en < 15:
        return "SLEEPY"
    if c.hu > 70 or c.ha < 30:
        return "SAD"
    if c.ha > 60 and c.hu < 50:
        return "HAPPY"
    return "NORMAL"


def creature_tick(c: Creature, dt: int = 30) -> None:
    steps = dt // 30
    if steps == 0:
        steps = 1
    for _ in range(steps):
        c.age += 30
        c.hu = min(100, c.hu + TICK_HUNGER_UP)
        for k in range(3):
            c.habit[k] = c.habit[k] - 8 if c.habit[k] > 8 else 0
        night = creature_night(c.age)
        if c.action == "SLEEP":
            c.sleeping = True
            c.en = min(100, c.en + (TICK_SLEEP_RECOVER_NIGHT if night else TICK_SLEEP_RECOVER_DAY))
        else:
            c.sleeping = False
            c.en = c.en - TICK_ENERGY_DOWN if c.en > TICK_ENERGY_DOWN else 0
        if c.action == "EAT" and c.hu > 0:
            c.hu = c.hu - TICK_EAT_HUNGER_DOWN if c.hu > TICK_EAT_HUNGER_DOWN else 0
        if c.action == "PLAY":
            c.ha = min(100, c.ha + TICK_PLAY_HAPPY_UP)
            # FW準拠: energy 1〜4でも消費して0に落とす (旧再現は>4のみで不死バグを再現していた)
            c.en = c.en - TICK_PLAY_ENERGY_DOWN if c.en > TICK_PLAY_ENERGY_DOWN else 0
        else:
            c.ha = c.ha - 1 if c.ha > 0 else 0
        if ((c.age // 30) % 2) == 0 and c.cl > 0:
            c.cl -= 1
        old = c.age > OLD_AGE_SEC
        if c.hu >= 95 or c.en == 0:
            if c.hp > 0:
                c.hp -= 1
        elif not old and c.hu < 50 and c.ha > 50 and c.hp < 100:
            c.hp += 1
        if old and c.hp > 0:
            c.hp -= 1


# --- ai.h ---
def _s_sleep(c: Creature) -> int:
    s = 90 if c.en < 25 else (55 if c.en < 50 else (5 if c.en > 80 else 10))
    if c.action == "SLEEP":
        s = min(100, s + 20)
    if creature_night(c.age):
        s = min(100, s + 20)
    return s


def _s_eat(c: Creature) -> int:
    return 85 if c.hu > 75 else (55 if c.hu > 50 else 10)


def _s_play(c: Creature) -> int:
    if c.en < 30:
        return 5
    s = 60 if c.ha < 40 else 20
    if creature_night(c.age):
        s -= 10
    return max(0, s)


def _s_explore(c: Creature) -> int:
    if c.en < 50:
        return 5
    s = 20 + c.cu // 3
    s += 10 if not creature_night(c.age) else -10
    return max(0, min(100, s))


def _s_comm(c: Creature) -> int:
    return c.so // 4


def _s_fight(c: Creature) -> int:
    return 45 if (c.ag > 60 and c.hp > 70) else 0


def ai_decide(c: Creature, peers: int = 0) -> str:
    table = [("SLEEP", _s_sleep(c)), ("EAT", _s_eat(c)), ("PLAY", _s_play(c)),
             ("EXPLORE", _s_explore(c)), ("COMM", _s_comm(c)),
             ("FIGHT", 0 if peers == 0 else _s_fight(c))]
    best, best_score = "IDLE", 30
    cur_score = 30 if c.action == "IDLE" else 0
    for a, s in table:
        if a == "COMM" and peers > 0:
            s = 40 + c.so // 4
        if a == c.action:
            cur_score = s
        if s > best_score:
            best_score, best = s, a
    return best if best_score > cur_score + 10 else c.action


# --- actions.h ---
def ui_feed(c: Creature) -> str:
    if c.hu == 0:
        c.ha = min(100, c.ha + hab_gain(2, c.habit[0]))
        c.action = "EAT"
        return "STUFFED"
    c.hu = c.hu - 30 if c.hu > 30 else 0
    c.ha = min(100, c.ha + hab_gain(5, c.habit[0]))
    c.habit[0] = min(100, c.habit[0] + 25)
    c.action = "EAT"
    return "FEED_OK"


def ui_play(c: Creature) -> str:
    if c.en < 10:
        return "LOW_ENERGY"
    c.ha = min(100, c.ha + hab_gain(25, c.habit[1]))
    c.habit[1] = min(100, c.habit[1] + 25)
    c.en -= 10
    c.action = "PLAY"
    return "PLAY_OK"


def ui_train(c: Creature, rng, target_trait: int = -1):
    """戻り値 (event, res, target, gain)。FW ui::train そのまま。"""
    raw = c.species % 12
    if 0 <= target_trait <= 3:
        target = target_trait
    else:
        target = APTITUDE[raw][0] if (rng() % 100) < TRAIN_AUTO_P else APTITUDE[raw][1]
    if c.en < TRAIN_OVERWORK_EN:
        c.hp = c.hp - 5 if c.hp > 5 else 1
        c.ha = c.ha - 10 if c.ha > 10 else 0
        c.action = "IDLE"
        return ("OVERWORK", "OVERWORK", target, 0)
    c.en = c.en - TRAIN_ENERGY_COST if c.en >= TRAIN_ENERGY_COST else 0
    c.hu = min(100, c.hu + TRAIN_HUNGER_COST)
    c.ha = c.ha - TRAIN_HAPPINESS_COST if c.ha >= TRAIN_HAPPINESS_COST else 0
    r = rng() % 100
    slack = (50 - c.ha) // 3 + 3 if c.ha < 50 else 3
    if r < slack:
        c.ha = min(100, c.ha + 8)
        c.action = "PLAY"
        return ("TR:SLACK", "SLACK", target, 0)
    r -= slack
    great = TRAIN_GREAT_HIGH if (c.ha >= 70 and c.en >= 50) else TRAIN_GREAT_LOW
    if r < great:
        gain = TRAIN_GREAT_BASE + (rng() % 2)
        _add_trait(c, target, gain)
        c.ha = min(100, c.ha + 15)
        c.action = "PLAY"
        return ("TR:GREAT!", "GREAT", target, gain)
    r -= great
    success = 40 + c.en * 4 // 10
    if r < success:
        gain = TRAIN_SUCCESS_BASE + (rng() % 2)
        _add_trait(c, target, gain)
        c.action = "PLAY"
        return ("TR:SUCCESS", "SUCCESS", target, gain)
    c.action = "IDLE"
    return ("TR:FAIL", "FAIL", target, 0)


def _add_trait(c: Creature, target: int, gain: int) -> None:
    if target == 0:
        c.in_ = min(100, c.in_ + gain)
    elif target == 1:
        c.ag = min(100, c.ag + gain)
    elif target == 2:
        c.cu = min(100, c.cu + gain)
    else:
        c.so = min(100, c.so + gain)


# --- battle (InkLife.ino reactPeer) ---
def morph_of(species: int) -> int:
    return species % 12


def family_of(species: int) -> int:
    return morph_of(species) % 3


def family_beats(fa: int, fb: int) -> bool:
    return fa != fb and (fa + 1) % 3 == fb


def fight_once(mine_ag: int, their_power: int, rng, fam_bonus: bool = False) -> bool:
    mine = mine_ag + rng() % FIGHT_RAND + (FIGHT_FAMILY_BONUS if fam_bonus else 0)
    theirs = their_power + rng() % FIGHT_RAND
    return mine >= theirs if FIGHT_WIN_TIE else mine > theirs


def greet_gain(fa: int, habit_soc: int, known_family: bool) -> int:
    if known_family:
        tot = 5 + cxx_div(fa, 25)
    elif fa is None:
        tot = 4
    else:
        tot = 3 + cxx_div(fa, 25)
    tot = hab_gain(tot, habit_soc) if tot >= 0 else 0
    return max(0, min(10, tot))


# --------------------------------------------------------------------------
# スイープ
# --------------------------------------------------------------------------
def cmd_train_dist(seed: int = 1) -> None:
    R = random.Random(seed)

    def rng() -> int:
        return R.getrandbits(32)  # esp_random() 相当 (uint32一様)
    print("== train outcome distribution (FW式, 20000試行/条件) ==")
    print(" en  ha |  SLACK  GREAT SUCCESS   FAIL OVERWORK | 平均gain/回")
    for en, ha in [(90, 80), (60, 60), (40, 40), (20, 20), (10, 80), (90, 10)]:
        cnt = {"SLACK": 0, "GREAT": 0, "SUCCESS": 0, "FAIL": 0, "OVERWORK": 0}
        tot_gain = 0
        N = 20000
        for _ in range(N):
            c = Creature(en=en, ha=ha, hu=20)
            _ev, res, _t, gain = ui_train(c, rng, target_trait=0)
            cnt[res] += 1
            tot_gain += gain
        print(f"{en:3d} {ha:3d} | {cnt['SLACK']/N:6.1%} {cnt['GREAT']/N:6.1%} "
              f"{cnt['SUCCESS']/N:6.1%} {cnt['FAIL']/N:6.1%} {cnt['OVERWORK']/N:6.1%} | {tot_gain/N:.3f}")


def cmd_grind(sessions: int = 200, seed: int = 1) -> None:
    """育成周回: TRAIN→(空腹ならFEED/疲労ならSLEEP+tick)の自動介護で何セッション回せるか."""
    R = random.Random(seed)

    def rng() -> int:
        return R.getrandbits(32)
    c = Creature(en=90, ha=70, hu=20, tr=(50, 50, 30, 40), species=250)
    gains = [0, 0, 0, 0]
    res_cnt: dict = {}
    rests = feeds = overworks = 0
    for _ in range(sessions):
        if c.hp == 0:
            break
        if c.hu > 60:
            ui_feed(c)
            feeds += 1
            creature_tick(c)
            continue
        if c.en < TRAIN_OVERWORK_EN + TRAIN_ENERGY_COST:
            c.action = "SLEEP"
            creature_tick(c)
            rests += 1
            continue
        _ev, res, t, gain = ui_train(c, rng)
        res_cnt[res] = res_cnt.get(res, 0) + 1
        gains[t] += gain
        if res == "OVERWORK":
            overworks += 1
        creature_tick(c)  # 30秒経過
    done = sum(res_cnt.values())
    print(f"== grind: {sessions}枠中 {done}回TRAIN (rest {rests}, feed {feeds}) ==")
    print(f"  結果内訳: {res_cnt}")
    print(f"  形質gain: INT+{gains[0]} AGGR+{gains[1]} CURIO+{gains[2]} SOC+{gains[3]} "
          f"(計+{sum(gains)}, 1回平均 {sum(gains)/max(1,done):.2f})")
    print(f"  最終: hp={c.hp} hu={c.hu} en={c.en} ha={c.ha} "
          f"tr=({c.in_},{c.cu},{c.ag},{c.so}) age={c.age}s")


def cmd_fight(trials: int = 20000, seed: int = 1) -> None:
    R = random.Random(seed)

    def rng() -> int:
        return R.getrandbits(32)
    print(f"== FIGHT勝率 (mine>=theirs、rand%{FIGHT_RAND}) ==")
    print(f" 自AGGR vs 相手POW | 勝率 (同等/家族優位+{FIGHT_FAMILY_BONUS})")
    for ag, pw in [(30, 30), (50, 50), (50, 30), (30, 50), (70, 40), (40, 70), (90, 50)]:
        w0 = sum(fight_once(ag, pw, rng, False) for _ in range(trials))
        w1 = sum(fight_once(ag, pw, rng, True) for _ in range(trials))
        print(f"  {ag:3d} vs {pw:3d}      | {w0/trials:6.1%}      {w1/trials:6.1%}")
    # 振れ幅の支配度: 差0で勝率≈51.7%(引分勝ち)、差10で?
    print("-- 差分特性 (優位なし) --")
    for d in [0, 5, 10, 15, 20, 30]:
        w = sum(fight_once(50 + d, 50, rng, False) for _ in range(trials))
        print(f"  差+{d:2d} | {w/trials:6.1%}")


def cmd_life(days: float = 3.0, seed: int = 1) -> None:
    """放置寿命: AIにおまかせ＋空腹90でFEEDだけする最小介護で何時間生きるか."""
    rng = random.Random(seed)
    rows = []
    for trial in range(5):
        c = Creature(en=90, ha=70, hu=20, tr=(50, 50, 30, 40),
                     species=250 + trial, age=0)
        t = 0
        steps = int(days * 86400 / 30)
        death = None
        for i in range(steps):
            c.action = ai_decide(c, peers=0)
            if c.hu > 85:  # 最小介護: 餌だけやる
                ui_feed(c)
            creature_tick(c)
            t += 30
            if c.hp == 0:
                death = t
                break
        rows.append((death, c.hp, c.en, c.hu, c.ha, c.age))
    print(f"== 放置寿命 (最小介護・AI行動、{days}日分・5個体) ==")
    for i, (death, hp, en, hu, ha, age) in enumerate(rows):
        if death is None:
            print(f"  個体{i}: 生存 age={age//3600}h hp={hp} en={en} hu={hu} ha={ha}")
        else:
            print(f"  個体{i}: 死亡 {death//3600}h{death%3600//60:02d}m "
                  f"(hp=0, hu={hu} en={en})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="InkLife FW balance simulator")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "train-dist", "grind", "fight", "life"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sessions", type=int, default=200)
    ap.add_argument("--trials", type=int, default=20000)
    ap.add_argument("--days", type=float, default=3.0)
    a = ap.parse_args(argv)
    if a.cmd in ("all", "train-dist"):
        cmd_train_dist(a.seed)
        print()
    if a.cmd in ("all", "grind"):
        cmd_grind(a.sessions, a.seed)
        print()
    if a.cmd in ("all", "fight"):
        cmd_fight(a.trials, a.seed)
        print()
    if a.cmd in ("all", "life"):
        cmd_life(a.days, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
