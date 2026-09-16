# pc-companion/tournament.py
"""
InkLife PC Companion - MF2 Style Tournament & 3D Battle Arena Engine
====================================================================
- 8-Chimera Single Elimination Tournament (Player + LoRa Peers + CPU Rivals)
- Grade System (F to S) & 4 Core Attributes (POW, INT, SPD, SKI)
- 100ms Real-Time Battle Math (Guts Regen, Strike/Blast/Evade, Dice Roll Accuracy)
- Fully 3D Cyber Stadium Arena (Dynamic Camera, Hitstop, Screen Shake, Light Pillars)
- 100% Clean ASCII/English Arcade UI (Zero Font Corruption / Zero '????' Glyphs)
- Dual Control: Keyboard (A/D/J/K/SPACE) AND Mouse Clickable Action Cards
- Hardware Fatigue Feedback (TOURNEY <energy_loss> <hunger_gain> <win>)
"""

import math
import random
import time
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Callable
import pyray as rl

from inkparser import (
    CreatureState, PeerInfo, MORPH_NAMES, GEAR_NAMES_EN,
    stat_rank, fuse_shown_gears, base_morph_of
)
from voxel_art import ChimeraVoxelModel
from sound_effects import SoundManager

# =============================================================================
# 1. Grade Constants & Morph Aptitude
# =============================================================================

GRADES = ["F", "E", "D", "C", "B", "A", "S"]

GRADE_THRESHOLDS = {
    "F": (0, 79),
    "E": (80, 149),
    "D": (150, 209),
    "C": (210, 269),
    "B": (270, 319),
    "A": (320, 359),
    "S": (360, 400),
}

GRADE_TOTAL_MID = {
    "F": 60, "E": 115, "D": 180, "C": 240, "B": 295, "A": 340, "S": 380
}

# (Primary Stat, Secondary Stat)
# FW src/ui/actions.h MORPH_TRAIT_APTITUDE と完全対応 (0:INT->INT, 1:AGGR->POW, 2:CURIO->SPD, 3:SOC->SKI)。
# 以前はほぼ全形態で不一致 (狐は逆、星は別物) だったため、育成適性と大会性能が乖離していた。
SPECIES_AFFINITY = {
    0: ("INT", "SKI"),  # SLIME  (INT, SOC)
    1: ("POW", "SPD"),  # DRAGON (AGGR, CURIO)
    2: ("SKI", "INT"),  # SHIBA  (SOC, INT)
    3: ("POW", "SPD"),  # SPINE  (AGGR, CURIO)
    4: ("SPD", "POW"),  # CAT    (CURIO, AGGR)
    5: ("INT", "SPD"),  # HALO   (INT, CURIO)
    6: ("SPD", "SKI"),  # FIN    (CURIO, SOC)
    7: ("SKI", "INT"),  # FROG   (SOC, INT)
    8: ("INT", "SKI"),  # SPIRAL (INT, SOC)
    9: ("POW", "INT"),  # LEG    (AGGR, INT)
    10: ("INT", "SPD"), # WHISKER/FOX (INT, CURIO)
    11: ("SKI", "SPD"), # STAR   (SOC, CURIO)
}

RIVAL_NAME_PREFIXES = [
    "Swift ", "Iron ", "Blaze ", "Shadow ", "Thunder ",
    "Ancient ", "Wild ", "Silver ", "Golden ", "Phantom ",
    "Cyber ", "Apex ", "Storm ", "Frost ", "Nova "
]

def get_grade_from_total(total: int) -> str:
    for g in GRADES:
        low, high = GRADE_THRESHOLDS[g]
        if low <= total <= high:
            return g
    return "S" if total > 400 else "F"


# =============================================================================
# 2. Fighter (Battle Data Model)
# =============================================================================

class FighterState(Enum):
    IDLE = auto()
    MOVING_FORWARD = auto()
    MOVING_BACK = auto()
    WINDUP_MELEE = auto()
    WINDUP_RANGED = auto()
    ATTACK_MELEE = auto()
    ATTACK_RANGED = auto()
    EVADE = auto()
    HIT = auto()
    KO = auto()

class Fighter:
    """1 Chimera Combatant Parameters and Runtime State"""
    def __init__(
        self,
        name: str,
        species: int,
        stats: Dict[str, int],
        fuse: Optional[List[int]] = None,
        is_cpu: bool = True,
        is_player: bool = False
    ):
        self.name = name
        self.species = species % 12
        self.stats = dict(stats)  # {"POW": int, "INT": int, "SPD": int, "SKI": int}
        self.fuse = list(fuse) if fuse else [255, 255, 255, 255]
        self.is_cpu = is_cpu
        self.is_player = is_player

        self.total_stats = sum(self.stats.values())
        self.grade = get_grade_from_total(self.total_stats)

        # Max HP
        # バランス修正: 旧式 60+(POW+INT)*0.5 は2-3発KOの秒殺ゲーだった。
        # 新式 80+(POW+INT)*0.6 で中堅4発・高域3発に調整 (MF2の長期戦寄り)。
        pow_val = self.stats.get("POW", 10)
        int_val = self.stats.get("INT", 10)
        self.max_hp = 80 + round((pow_val + int_val) * 0.6)
        self.hp = self.max_hp

        # Dynamic Battle State
        self.guts: float = 20.0
        self.fstate: FighterState = FighterState.IDLE
        self.state_timer: float = 0.0

        # 3D Animation Offsets
        self.anim_offset_x: float = 0.0
        self.anim_offset_y: float = 0.0
        self.squash_x: float = 1.0
        self.squash_y: float = 1.0
        self.rot_z: float = 0.0
        self.hit_flash: float = 0.0

    @classmethod
    def from_creature_state(cls, state: CreatureState) -> "Fighter":
        stats = {
            "POW": state.aggression,
            "INT": state.intelligence,
            "SPD": state.curiosity,
            "SKI": state.sociability
        }
        return cls(
            name=f"My {state.base_name}",
            species=state.species_id,
            stats=stats,
            fuse=state.fuse,
            is_cpu=False,
            is_player=True
        )

    @classmethod
    def from_peer(cls, peer: PeerInfo, target_grade: str) -> "Fighter":
        # +AFF系では種が送られないため species==0 (スライム) のままが多い。
        # 全員スライム大会になるのを避け、DIDハッシュで12形態に分散させる。
        if peer.species % 12 == 0:
            seed_chk = hash(peer.did) & 0xFFFFFF
            species = (seed_chk % 12)
            # 0が本物スライムの可能性もあるため、1/12は0のまま残す
            if species == 0 and (seed_chk % 3) != 0:
                species = 1 + (seed_chk % 11)
        else:
            species = peer.species % 12
        base_total = GRADE_TOTAL_MID.get(target_grade, 200)
        seed_val = hash(peer.did) & 0xFFFFFF
        rng = random.Random(seed_val)

        a_stat, b_stat = SPECIES_AFFINITY[species]
        stats = {"POW": 10, "INT": 10, "SPD": 10, "SKI": 10}
        stats[a_stat] += int(base_total * 0.32)
        stats[b_stat] += int(base_total * 0.22)
        rem = max(0, base_total - sum(stats.values()))
        keys = list(stats.keys())
        for _ in range(rem):
            stats[rng.choice(keys)] += 1

        fuse = [rng.choice(range(12)) if rng.random() < 0.4 else 255 for _ in range(4)]
        return cls(
            name=f"Peer {peer.did[-4:]}",
            species=species,
            stats=stats,
            fuse=fuse,
            is_cpu=True,
            is_player=False
        )

    @classmethod
    def create_cpu_rival(cls, grade: str) -> "Fighter":
        species = random.randint(0, 11)
        a_stat, b_stat = SPECIES_AFFINITY[species]
        base_total = GRADE_TOTAL_MID.get(grade, 200)

        stats = {"POW": 10, "INT": 10, "SPD": 10, "SKI": 10}
        stats[a_stat] += int(base_total * 0.34)
        stats[b_stat] += int(base_total * 0.21)
        rem = max(0, base_total - sum(stats.values()))
        keys = list(stats.keys())
        for _ in range(rem):
            stats[random.choice(keys)] += 1

        for k in stats:
            noise = random.randint(-4, 4)
            stats[k] = max(5, stats[k] + noise)

        fuse = [255, 255, 255, 255]
        if random.random() < 0.7:
            fuse[0] = random.randint(0, 11)
        if random.random() < 0.4:
            fuse[1] = random.randint(0, 11)

        prefix = random.choice(RIVAL_NAME_PREFIXES)
        sp_name = MORPH_NAMES.get(species, "CHIMERA")
        name = f"{prefix}{sp_name}"

        return cls(
            name=name,
            species=species,
            stats=stats,
            fuse=fuse,
            is_cpu=True,
            is_player=False
        )

    def reset_for_battle(self):
        self.hp = self.max_hp
        self.guts = 20.0
        self.fstate = FighterState.IDLE
        self.state_timer = 0.0
        self.anim_offset_x = 0.0
        self.anim_offset_y = 0.0
        self.squash_x = 1.0
        self.squash_y = 1.0
        self.rot_z = 0.0
        self.hit_flash = 0.0


# =============================================================================
# 3. BattleEngine (Real-Time 100ms Combat Math)
# =============================================================================

class MoveType(Enum):
    NONE = auto()
    FORWARD = auto()
    BACK = auto()
    MELEE = auto()
    RANGED = auto()
    EVADE = auto()

class BattleEvent(Enum):
    GONG = auto()
    MOVE_MELEE = auto()
    MOVE_RANGED = auto()
    HIT_PUNCH = auto()
    HIT_MAGIC = auto()
    EVADE_SUCCESS = auto()
    MISS = auto()
    KO = auto()
    TIME_UP = auto()

class BattleEngine:
    """MF2-style Real-Time Battle Simulation Engine"""
    def __init__(self, fighter_a: Fighter, fighter_b: Fighter, time_limit_s: float = 30.0):
        self.a = fighter_a
        self.b = fighter_b
        self.time_limit = time_limit_s
        self.time_left = time_limit_s

        self.distance = 50.0  # Range: 0 (close) .. 100 (far)
        self.a.reset_for_battle()
        self.b.reset_for_battle()

        self.events: List[BattleEvent] = [BattleEvent.GONG]
        self.hit_stop: float = 0.0
        self.shake_time: float = 0.0
        self.winner: Optional[Fighter] = None
        self.is_finished: bool = False
        self.end_reason: str = ""

        # Damage popups: [(text, x, y, life, col)]
        self.popups: List[dict] = []

    def tick(self, dt: float, action_a: MoveType, action_b: MoveType):
        if self.is_finished:
            return

        if self.hit_stop > 0.0:
            self.hit_stop -= dt
            return

        self.time_left = max(0.0, self.time_left - dt)
        if self.shake_time > 0.0:
            self.shake_time = max(0.0, self.shake_time - dt)

        # 1. Guts Regeneration
        guts_rate_a = 3.0 + self.a.stats.get("SPD", 10) * 0.04
        guts_rate_b = 3.0 + self.b.stats.get("SPD", 10) * 0.04
        self.a.guts = min(99.0, self.a.guts + guts_rate_a * dt)
        self.b.guts = min(99.0, self.b.guts + guts_rate_b * dt)

        # Update popups
        for p in self.popups:
            p["y"] += p["vy"] * dt
            p["life"] -= dt
        self.popups = [p for p in self.popups if p["life"] > 0.0]

        # Hit flashes
        self.a.hit_flash = max(0.0, self.a.hit_flash - dt * 5.0)
        self.b.hit_flash = max(0.0, self.b.hit_flash - dt * 5.0)

        # 2. Update Fighter Actions
        self._update_fighter_state(self.a, self.b, action_a, dt, is_attacker_left=True)
        self._update_fighter_state(self.b, self.a, action_b, dt, is_attacker_left=False)

        # 3. Check Victory
        if self.a.hp <= 0 or self.b.hp <= 0:
            self.is_finished = True
            if self.a.hp <= 0 and self.b.hp <= 0:
                self.winner = self.a if self.a.stats.get("SKI", 10) >= self.b.stats.get("SKI", 10) else self.b
            elif self.a.hp <= 0:
                self.winner = self.b
                self.a.fstate = FighterState.KO
            else:
                self.winner = self.a
                self.b.fstate = FighterState.KO
            self.events.append(BattleEvent.KO)
            self.end_reason = "K.O. !!"
            self.shake_time = 0.5
            return

        if self.time_left <= 0.0:
            self.is_finished = True
            self.events.append(BattleEvent.TIME_UP)
            self._resolve_time_up()

    def _update_fighter_state(
        self,
        actor: Fighter,
        target: Fighter,
        action: MoveType,
        dt: float,
        is_attacker_left: bool
    ):
        if actor.fstate == FighterState.KO:
            return

        spd = actor.stats.get("SPD", 10)
        # バランス修正: 旧 14+SPD*0.18 は両者前進で46/sと速すぎ (1秒で間合い消失)。
        # 新 10+SPD*0.12 で片方16/s・両方32/sに抑制。BACKは0.8倍で前進有利。
        closing_speed = 10.0 + spd * 0.12

        # Windup & recovery timers
        if actor.fstate in (FighterState.WINDUP_MELEE, FighterState.WINDUP_RANGED, FighterState.EVADE, FighterState.HIT):
            actor.state_timer -= dt
            if actor.state_timer <= 0.0:
                if actor.fstate == FighterState.WINDUP_MELEE:
                    self._execute_move(actor, target, MoveType.MELEE, is_attacker_left)
                elif actor.fstate == FighterState.WINDUP_RANGED:
                    self._execute_move(actor, target, MoveType.RANGED, is_attacker_left)
                actor.fstate = FighterState.IDLE
                actor.anim_offset_x = 0.0
                actor.squash_y = 1.0
            return

        actor.anim_offset_x = 0.0
        actor.squash_y = 1.0

        if action == MoveType.FORWARD:
            self.distance = max(5.0, self.distance - closing_speed * dt)
            actor.fstate = FighterState.MOVING_FORWARD
            actor.anim_offset_x = 0.12 if is_attacker_left else -0.12
        elif action == MoveType.BACK:
            self.distance = min(95.0, self.distance + closing_speed * 0.8 * dt)
            actor.fstate = FighterState.MOVING_BACK
            actor.anim_offset_x = -0.08 if is_attacker_left else 0.08
        # バランス修正: 旧 MELEE<=30 / RANGED>=40 は31-39がデッドゾーンで両カード無効。
        # 新 MELEE<=32 / RANGED>=30 でオーバーラップ (30-32は両方可、役割分担は維持)。
        elif action == MoveType.MELEE and actor.guts >= 15.0 and self.distance <= 32.0:
            actor.guts -= 15.0
            actor.fstate = FighterState.WINDUP_MELEE
            actor.state_timer = 0.20
            actor.anim_offset_x = 0.25 if is_attacker_left else -0.25
            self.events.append(BattleEvent.MOVE_MELEE)
        elif action == MoveType.RANGED and actor.guts >= 25.0 and self.distance >= 30.0:
            actor.guts -= 25.0
            actor.fstate = FighterState.WINDUP_RANGED
            actor.state_timer = 0.55
            actor.squash_y = 1.25
            self.events.append(BattleEvent.MOVE_RANGED)
        elif action == MoveType.EVADE and actor.guts >= 10.0:
            actor.guts -= 10.0
            actor.fstate = FighterState.EVADE
            actor.state_timer = 0.28
            actor.squash_y = 0.65
            actor.anim_offset_x = -0.22 if is_attacker_left else 0.22
            self.events.append(BattleEvent.EVADE_SUCCESS)
        else:
            actor.fstate = FighterState.IDLE

    def _execute_move(self, atk: Fighter, defn: Fighter, move: MoveType, is_attacker_left: bool):
        ski_atk = atk.stats.get("SKI", 10)
        spd_def = defn.stats.get("SPD", 10)

        # Hit rate clamp(55 + (SKI - SPD)*0.35 + (guts_a - guts_b)*0.05, 10, 95)
        hit_rate = 55.0 + (ski_atk - spd_def) * 0.35 + (atk.guts - defn.guts) * 0.05
        hit_rate = max(10.0, min(95.0, hit_rate))

        is_evading = (defn.fstate == FighterState.EVADE)
        dice = random.uniform(0.0, 100.0)

        popup_x = 0.8 if is_attacker_left else -0.8
        popup_y = 1.4

        if is_evading:
            defn.guts = max(0.0, defn.guts - 5.0)
            self.events.append(BattleEvent.EVADE_SUCCESS)
            self.popups.append({
                "text": "EVADE!", "x": popup_x, "y": popup_y, "vy": 0.6, "life": 1.2,
                "col": rl.Color(80, 220, 255, 255)
            })
            return

        if dice > hit_rate:
            self.events.append(BattleEvent.MISS)
            self.popups.append({
                "text": "MISS", "x": popup_x, "y": popup_y, "vy": 0.4, "life": 1.0,
                "col": rl.Color(160, 175, 190, 255)
            })
            return

        if move == MoveType.MELEE:
            pow_val = atk.stats.get("POW", 10)
            # バランス修正: 旧 POW*0.9 は2-3発KO。POW*0.55+8で中堅4発・高域3発に。
            base_dmg = pow_val * 0.55 + 8 + random.randint(-5, 5)
            self.events.append(BattleEvent.HIT_PUNCH)
        else:
            int_val = atk.stats.get("INT", 10)
            # 旧 INT*1.15 は遠距離優位すぎ。INT*0.65+10で近接と同等に。
            base_dmg = int_val * 0.65 + 10 + random.randint(-7, 7)
            self.events.append(BattleEvent.HIT_MAGIC)

        # Critical Roll (旧 SKI*0.35最大40%は多すぎ。SKI*0.25最大25%に抑制)
        crit_chance = max(0.0, min(25.0, ski_atk * 0.25))
        is_crit = (random.uniform(0.0, 100.0) < crit_chance)
        dmg = round(base_dmg * (1.6 if is_crit else 1.0))
        dmg = max(1, dmg)

        defn.hp = max(0, defn.hp - dmg)
        defn.fstate = FighterState.HIT
        defn.state_timer = 0.22
        defn.hit_flash = 1.0
        self.hit_stop = 0.08
        self.shake_time = 0.22 if is_crit else 0.12

        pop_text = f"CRITICAL! -{dmg}" if is_crit else f"-{dmg}"
        pop_col = rl.Color(255, 60, 60, 255) if is_crit else rl.Color(255, 210, 60, 255)
        self.popups.append({
            "text": pop_text, "x": popup_x, "y": popup_y, "vy": 0.7, "life": 1.4,
            "col": pop_col
        })

    def _resolve_time_up(self):
        ratio_a = self.a.hp / max(1, self.a.max_hp)
        ratio_b = self.b.hp / max(1, self.b.max_hp)

        if abs(ratio_a - ratio_b) > 0.01:
            self.winner = self.a if ratio_a > ratio_b else self.b
            self.end_reason = "TIME UP (HP%)"
        elif abs(self.a.guts - self.b.guts) > 1.0:
            self.winner = self.a if self.a.guts > self.b.guts else self.b
            self.end_reason = "TIME UP (GUTS)"
        else:
            ski_a = self.a.stats.get("SKI", 10)
            ski_b = self.b.stats.get("SKI", 10)
            prob_a = 0.65 if ski_a >= ski_b else 0.35
            self.winner = self.a if random.random() < prob_a else self.b
            self.end_reason = "TIME UP (DECISION)"


# =============================================================================
# 4. BattleAI (Utility-based Auto Combat AI)
# =============================================================================

class BattleAI:
    def __init__(self, is_aggressive: bool = False):
        self.is_aggressive = is_aggressive
        self.think_cooldown = 0.0
        self.current_action = MoveType.NONE

    def choose_action(self, me: Fighter, enemy: Fighter, distance: float, dt: float) -> MoveType:
        self.think_cooldown -= dt
        if self.think_cooldown > 0.0:
            return self.current_action

        self.think_cooldown = random.uniform(0.12, 0.22)

        # Reaction to enemy windup (旧70%は回避無双で試合が時間切ればかり。35%に抑制)
        if enemy.fstate in (FighterState.WINDUP_MELEE, FighterState.WINDUP_RANGED) and me.guts >= 10.0:
            if random.random() < 0.35:
                self.current_action = MoveType.EVADE
                return self.current_action

        pow_val = me.stats.get("POW", 10)
        int_val = me.stats.get("INT", 10)
        prefer_melee = pow_val >= int_val

        if prefer_melee:
            if distance <= 32.0:
                if me.guts >= 15.0:
                    self.current_action = MoveType.MELEE
                else:
                    self.current_action = MoveType.BACK
            else:
                self.current_action = MoveType.FORWARD
        else:
            if distance >= 30.0:
                if me.guts >= 25.0:
                    self.current_action = MoveType.RANGED
                else:
                    self.current_action = MoveType.NONE
            else:
                # 24-30m帯はBLAST圏外のため下がって間合いを取り直す (旧コイン投げ停留)
                self.current_action = MoveType.BACK

        return self.current_action


# =============================================================================
# 5. TournamentManager (Bracket & Match Advancement)
# =============================================================================

class Match:
    def __init__(self, match_id: int, round_idx: int, fighter_a: Optional[Fighter], fighter_b: Optional[Fighter]):
        self.match_id = match_id
        self.round_idx = round_idx
        self.fighter_a = fighter_a
        self.fighter_b = fighter_b
        self.winner: Optional[Fighter] = None
        self.completed = False

    @property
    def is_player_involved(self) -> bool:
        return bool(
            (self.fighter_a and self.fighter_a.is_player) or
            (self.fighter_b and self.fighter_b.is_player)
        )

class TournamentManager:
    def __init__(self, my_fighter: Fighter, peers: List[PeerInfo]):
        self.my_fighter = my_fighter
        self.grade = my_fighter.grade
        self.peers = peers

        self.matches: List[Match] = []
        self.is_tournament_over = False
        self.champion: Optional[Fighter] = None
        self.player_eliminated = False
        self.player_won = False
        self.player_matches_played = 0

        self._build_bracket()

    def _build_bracket(self):
        slots: List[Fighter] = [self.my_fighter]

        valid_peers = [p for p in self.peers if p.known]
        valid_peers.sort(key=lambda p: p.aff, reverse=True)
        for p in valid_peers[:6]:
            slots.append(Fighter.from_peer(p, self.grade))

        while len(slots) < 8:
            slots.append(Fighter.create_cpu_rival(self.grade))

        rivals = slots[1:]
        random.shuffle(rivals)
        bracket_fighters = [slots[0]] + rivals

        self.matches = [
            Match(0, 0, bracket_fighters[0], bracket_fighters[1]),
            Match(1, 0, bracket_fighters[2], bracket_fighters[3]),
            Match(2, 0, bracket_fighters[4], bracket_fighters[5]),
            Match(3, 0, bracket_fighters[6], bracket_fighters[7]),
            Match(4, 1, None, None),
            Match(5, 1, None, None),
            Match(6, 2, None, None)
        ]

    def resolve_background_matches(self):
        for m in self.matches[1:4]:
            if not m.completed and m.fighter_a and m.fighter_b:
                m.winner = self._simulate_quick_match(m.fighter_a, m.fighter_b)
                m.completed = True

        if self.matches[1].completed and self.matches[0].completed:
            self.matches[4].fighter_a = self.matches[0].winner
            self.matches[4].fighter_b = self.matches[1].winner

        if self.matches[2].completed and self.matches[3].completed:
            self.matches[5].fighter_a = self.matches[2].winner
            self.matches[5].fighter_b = self.matches[3].winner
            if not self.matches[5].is_player_involved and not self.matches[5].completed:
                self.matches[5].winner = self._simulate_quick_match(self.matches[5].fighter_a, self.matches[5].fighter_b)
                self.matches[5].completed = True

        if self.matches[4].completed and self.matches[5].completed:
            self.matches[6].fighter_a = self.matches[4].winner
            self.matches[6].fighter_b = self.matches[5].winner

    def get_next_player_match(self) -> Optional[Match]:
        if self.player_eliminated or self.is_tournament_over:
            return None
        for m in (self.matches[0], self.matches[4], self.matches[6]):
            if not m.completed and m.fighter_a and m.fighter_b:
                return m
        return None

    def record_match_result(self, match: Match, winner: Fighter):
        match.winner = winner
        match.completed = True
        if match.is_player_involved:
            self.player_matches_played += 1
            if winner != self.my_fighter:
                self.player_eliminated = True

        self.resolve_background_matches()

        if self.matches[6].completed:
            self.is_tournament_over = True
            self.champion = self.matches[6].winner
            self.player_won = (self.champion == self.my_fighter)

    def _simulate_quick_match(self, a: Fighter, b: Fighter) -> Fighter:
        # 重複・同ゾーン敗北分は実効1つ扱い (表示フィルタと一致)
        r_a = a.total_stats + len(set(f for f in a.fuse if f < 12)) * 5
        r_b = b.total_stats + len(set(f for f in b.fuse if f < 12)) * 5
        # バランス修正: /60は能力差60で91%勝率の雪だるま式。/80で68%(差30)→76%(差60)に緩和。
        win_prob_a = 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 80.0))
        return a if random.random() < win_prob_a else b

    def compute_fatigue_payload(self) -> Tuple[int, int, int]:
        if self.player_won:
            return (40, 30, 1)
        elif self.player_matches_played == 3:
            return (35, 25, 0)
        elif self.player_matches_played == 2:
            return (25, 20, 0)
        else:
            return (18, 15, 0)


# =============================================================================
# 6. TournamentUI (3D Stadium Arena & Clean Arcade HUD)
# =============================================================================

class TournamentPhase(Enum):
    BRACKET = auto()
    COUNTDOWN = auto()
    BATTLE = auto()
    MATCH_RESULT = auto()
    VICTORY_SCREEN = auto()

class TournamentUI:
    """Full 3D Stage Presentation & Modern Interactive UX"""
    def __init__(self, manager: TournamentManager, sound_mgr: SoundManager):
        self.mgr = manager
        self.sound = sound_mgr
        self.phase = TournamentPhase.BRACKET

        self.current_match: Optional[Match] = None
        self.engine: Optional[BattleEngine] = None
        self.ai_enemy = BattleAI()
        self.ai_player = BattleAI()
        self.auto_battle = False

        self.model_a = ChimeraVoxelModel()
        self.model_b = ChimeraVoxelModel()

        # Dynamic 3D Camera
        self.cam_base_pos = rl.Vector3(0.0, 2.2, 4.4)
        self.cam_target = rl.Vector3(0.0, 0.75, 0.0)
        self.cam = rl.Camera3D(
            self.cam_base_pos,
            self.cam_target,
            rl.Vector3(0.0, 1.0, 0.0),
            40.0,
            rl.CAMERA_PERSPECTIVE
        )

        self.phase_timer = 0.0
        self.fatigue_sent = False
        self.should_exit = False
        # 呼吸モーション専用の単調時計 (engine.time_leftは残り時間のため逆行する)
        self.anim_t = 0.0

        # Clickable Card Rectangles
        self.btn_enter_arena = rl.Rectangle(440, 680, 400, 50)
        self.btn_melee_card = rl.Rectangle(320, 655, 160, 80)
        self.btn_ranged_card = rl.Rectangle(500, 655, 160, 80)
        self.btn_evade_card = rl.Rectangle(680, 655, 160, 80)
        self.btn_auto_toggle = rl.Rectangle(860, 670, 170, 42)
        self.btn_return_farm = rl.Rectangle(460, 640, 360, 52)

        self.mgr.resolve_background_matches()

    def start_next_match(self):
        m = self.mgr.get_next_player_match()
        if not m:
            if self.mgr.is_tournament_over or self.mgr.player_eliminated:
                self.phase = TournamentPhase.VICTORY_SCREEN
                if self.mgr.player_won:
                    self.sound.play("tourney_win")
            return

        self.current_match = m
        is_final = (m.round_idx == 2)
        time_limit = 45.0 if is_final else 30.0
        self.engine = BattleEngine(m.fighter_a, m.fighter_b, time_limit)
        self.phase = TournamentPhase.COUNTDOWN
        self.phase_timer = 2.0

        self.model_a.build(m.fighter_a.species, "IDLE", "NORMAL", m.fighter_a.fuse, 80)
        self.model_b.build(m.fighter_b.species, "IDLE", "NORMAL", m.fighter_b.fuse, 80)

    def update(self, dt: float, serial_worker) -> bool:
        if self.should_exit:
            return True
        self.anim_t += dt

        mouse_pos = rl.get_mouse_position()
        mouse_clicked = rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)

        if self.phase == TournamentPhase.BRACKET:
            enter_clicked = mouse_clicked and rl.check_collision_point_rec(mouse_pos, self.btn_enter_arena)
            if rl.is_key_pressed(rl.KEY_SPACE) or rl.is_key_pressed(rl.KEY_ENTER) or enter_clicked:
                self.sound.play("click")
                self.start_next_match()

        elif self.phase == TournamentPhase.COUNTDOWN:
            self.phase_timer -= dt
            if self.phase_timer <= 0.0:
                self.phase = TournamentPhase.BATTLE
                self.sound.play("battle_gong")

        elif self.phase == TournamentPhase.BATTLE:
            if not self.engine:
                return False

            # Toggle auto battle via mouse or TAB
            if (mouse_clicked and rl.check_collision_point_rec(mouse_pos, self.btn_auto_toggle)) or rl.is_key_pressed(rl.KEY_TAB):
                self.auto_battle = not self.auto_battle
                self.sound.play("click")

            action_a = MoveType.NONE

            if self.auto_battle:
                action_a = self.ai_player.choose_action(
                    self.engine.a, self.engine.b, self.engine.distance, dt
                )
            else:
                # Keyboard controls
                if rl.is_key_down(rl.KEY_D) or rl.is_key_down(rl.KEY_RIGHT):
                    action_a = MoveType.FORWARD
                elif rl.is_key_down(rl.KEY_A) or rl.is_key_down(rl.KEY_LEFT):
                    action_a = MoveType.BACK
                elif rl.is_key_pressed(rl.KEY_J) or rl.is_key_pressed(rl.KEY_Z):
                    action_a = MoveType.MELEE
                elif rl.is_key_pressed(rl.KEY_K) or rl.is_key_pressed(rl.KEY_X):
                    action_a = MoveType.RANGED
                elif rl.is_key_pressed(rl.KEY_SPACE) or rl.is_key_pressed(rl.KEY_C):
                    action_a = MoveType.EVADE

                # Mouse card click controls
                if mouse_clicked:
                    if rl.check_collision_point_rec(mouse_pos, self.btn_melee_card):
                        action_a = MoveType.MELEE
                    elif rl.check_collision_point_rec(mouse_pos, self.btn_ranged_card):
                        action_a = MoveType.RANGED
                    elif rl.check_collision_point_rec(mouse_pos, self.btn_evade_card):
                        action_a = MoveType.EVADE

            # CPU enemy AI
            action_b = self.ai_enemy.choose_action(
                self.engine.b, self.engine.a, self.engine.distance, dt
            )

            # Engine tick
            self.engine.tick(dt, action_a, action_b)

            # Sound triggers
            while self.engine.events:
                ev = self.engine.events.pop(0)
                if ev == BattleEvent.MOVE_MELEE:
                    self.sound.play("move_melee")
                elif ev == BattleEvent.MOVE_RANGED:
                    self.sound.play("move_ranged")
                elif ev == BattleEvent.HIT_PUNCH:
                    self.sound.play("hit_punch")
                elif ev == BattleEvent.HIT_MAGIC:
                    self.sound.play("hit_magic")
                elif ev == BattleEvent.EVADE_SUCCESS:
                    self.sound.play("evade")
                elif ev == BattleEvent.KO:
                    self.sound.play("battle_ko")

            if self.engine.is_finished:
                self.phase = TournamentPhase.MATCH_RESULT
                self.phase_timer = 3.0
                self.mgr.record_match_result(self.current_match, self.engine.winner)

        elif self.phase == TournamentPhase.MATCH_RESULT:
            self.phase_timer -= dt
            if self.phase_timer <= 0.0 or rl.is_key_pressed(rl.KEY_SPACE) or mouse_clicked:
                if self.mgr.is_tournament_over or self.mgr.player_eliminated:
                    self.phase = TournamentPhase.VICTORY_SCREEN
                    if self.mgr.player_won:
                        self.sound.play("tourney_win")
                else:
                    self.phase = TournamentPhase.BRACKET

        elif self.phase == TournamentPhase.VICTORY_SCREEN:
            if not self.fatigue_sent and serial_worker:
                el, hg, win = self.mgr.compute_fatigue_payload()
                serial_worker.send(f"TOURNEY {el} {hg} {win}\n")
                self.fatigue_sent = True

            return_clicked = mouse_clicked and rl.check_collision_point_rec(mouse_pos, self.btn_return_farm)
            if rl.is_key_pressed(rl.KEY_SPACE) or rl.is_key_pressed(rl.KEY_ESCAPE) or return_clicked:
                self.should_exit = True

        return False

    def draw(self, screen_w: int, screen_h: int):
        if self.phase == TournamentPhase.BRACKET:
            self._draw_bracket_screen(screen_w, screen_h)
        elif self.phase in (TournamentPhase.COUNTDOWN, TournamentPhase.BATTLE, TournamentPhase.MATCH_RESULT):
            self._draw_battle_screen(screen_w, screen_h)
        elif self.phase == TournamentPhase.VICTORY_SCREEN:
            self._draw_victory_screen(screen_w, screen_h)

    # -------------------------------------------------------------------------
    # Bracket Screen (Clean ASCII UI)
    # -------------------------------------------------------------------------
    def _draw_bracket_screen(self, w: int, h: int):
        rl.clear_background(rl.Color(16, 20, 28, 255))

        # Title & Header
        rl.draw_text("INKLIFE TOURNAMENT ARENA", 40, 24, 26, rl.Color(80, 220, 240, 255))
        grade_text = f"GRADE: {self.mgr.grade}-CLASS  |  8-CHIMERA SINGLE ELIMINATION BRACKET"
        rl.draw_text(grade_text, 40, 56, 14, rl.Color(160, 180, 200, 255))

        matches = self.mgr.matches
        x_r1 = 60
        x_r2 = 410
        x_r3 = 760

        # R1 (Match 0..3)
        for mi in range(4):
            m = matches[mi]
            y_top = 95 + mi * 135
            self._draw_match_box(m, x_r1, y_top, 270, 92)

        # R2 (Match 4..5)
        for mi in range(2):
            m = matches[4 + mi]
            y_top = 162 + mi * 270
            self._draw_match_box(m, x_r2, y_top, 270, 92)

        # R3 Final (Match 6)
        self._draw_match_box(matches[6], x_r3, 298, 290, 105, is_final=True)

        # Connector lines
        for mi in range(2):
            y1 = 141 + mi * 270
            y2 = 276 + mi * 270
            y_mid = (y1 + y2) // 2
            rl.draw_line(x_r1 + 270, y1, x_r1 + 340, y1, rl.Color(60, 80, 110, 255))
            rl.draw_line(x_r1 + 270, y2, x_r1 + 340, y2, rl.Color(60, 80, 110, 255))
            rl.draw_line(x_r1 + 340, y1, x_r1 + 340, y2, rl.Color(60, 80, 110, 255))
            rl.draw_line(x_r1 + 340, y_mid, x_r2, y_mid, rl.Color(60, 80, 110, 255))

        rl.draw_line(x_r2 + 270, 208, x_r2 + 320, 208, rl.Color(60, 80, 110, 255))
        rl.draw_line(x_r2 + 270, 478, x_r2 + 320, 478, rl.Color(60, 80, 110, 255))
        rl.draw_line(x_r2 + 320, 208, x_r2 + 320, 478, rl.Color(60, 80, 110, 255))
        rl.draw_line(x_r2 + 320, 350, x_r3, 350, rl.Color(60, 80, 110, 255))

        # Big Action Button: ENTER ARENA
        mouse_pos = rl.get_mouse_position()
        hover = rl.check_collision_point_rec(mouse_pos, self.btn_enter_arena)
        btn_bg = rl.Color(50, 75, 110, 255) if hover else rl.Color(35, 50, 75, 255)
        rl.draw_rectangle_rounded(self.btn_enter_arena, 0.3, 6, btn_bg)
        rl.draw_rectangle_rounded_lines(self.btn_enter_arena, 0.3, 6, rl.Color(255, 215, 0, 255) if hover else rl.Color(80, 220, 240, 255))

        enter_lbl = ">> ENTER ARENA (NEXT MATCH) <<"
        tw = rl.measure_text(enter_lbl, 18)
        tx = int(self.btn_enter_arena.x + (self.btn_enter_arena.width - tw) / 2)
        ty = int(self.btn_enter_arena.y + 16)
        rl.draw_text(enter_lbl, tx, ty, 18, rl.Color(255, 220, 60, 255) if hover else rl.WHITE)

    def _draw_match_box(self, match: Match, x: int, y: int, bw: int, bh: int, is_final: bool = False):
        bg_col = rl.Color(28, 36, 50, 255)
        border_col = rl.Color(255, 200, 50, 255) if match.is_player_involved else rl.Color(50, 65, 88, 255)
        if is_final:
            border_col = rl.Color(255, 100, 160, 255)

        rl.draw_rectangle_rounded(rl.Rectangle(x, y, bw, bh), 0.15, 4, bg_col)
        rl.draw_rectangle_rounded_lines(rl.Rectangle(x, y, bw, bh), 0.15, 4, border_col)

        # Fighter A
        fa = match.fighter_a
        name_a = fa.name if fa else "TBD"
        col_a = rl.Color(80, 230, 255, 255) if (fa and fa.is_player) else rl.Color(230, 238, 248, 255)
        if match.winner and match.winner != fa:
            col_a = rl.Color(95, 105, 120, 255)
        elif match.winner and match.winner == fa:
            name_a = "[WIN] " + name_a
            col_a = rl.Color(255, 215, 0, 255)

        rl.draw_text(name_a[:18], x + 12, y + 14, 13, col_a)
        if fa:
            rl.draw_text(f"P:{fa.stats['POW']} I:{fa.stats['INT']}", x + 175, y + 14, 11, rl.Color(150, 170, 195, 255))

        rl.draw_line(x + 10, y + bh // 2, x + bw - 10, y + bh // 2, rl.Color(42, 52, 70, 255))

        # Fighter B
        fb = match.fighter_b
        name_b = fb.name if fb else "TBD"
        col_b = rl.Color(80, 230, 255, 255) if (fb and fb.is_player) else rl.Color(230, 238, 248, 255)
        if match.winner and match.winner != fb:
            col_b = rl.Color(95, 105, 120, 255)
        elif match.winner and match.winner == fb:
            name_b = "[WIN] " + name_b
            col_b = rl.Color(255, 215, 0, 255)

        rl.draw_text(name_b[:18], x + 12, y + bh // 2 + 14, 13, col_b)
        if fb:
            rl.draw_text(f"P:{fb.stats['POW']} I:{fb.stats['INT']}", x + 175, y + bh // 2 + 14, 11, rl.Color(150, 170, 195, 255))

    # -------------------------------------------------------------------------
    # Full 3D Stadium Battle Arena
    # -------------------------------------------------------------------------
    def _draw_battle_screen(self, w: int, h: int):
        if not self.engine:
            return

        rl.clear_background(rl.Color(10, 14, 22, 255))

        # Camera Shake on Hit
        shake_x = 0.0
        shake_y = 0.0
        if self.engine.shake_time > 0.0:
            shake_amp = self.engine.shake_time * 0.25
            shake_x = random.uniform(-shake_amp, shake_amp)
            shake_y = random.uniform(-shake_amp, shake_amp)

        # Dynamic Dolly Camera
        dolly_zoom = 0.0
        if self.engine.a.fstate in (FighterState.WINDUP_MELEE, FighterState.WINDUP_RANGED):
            dolly_zoom = 0.45

        self.cam.position.x = self.cam_base_pos.x + shake_x
        self.cam.position.y = self.cam_base_pos.y + shake_y
        self.cam.position.z = self.cam_base_pos.z - dolly_zoom

        # ---------------------------------------------------------------------
        # 3D Scene Rendering
        # ---------------------------------------------------------------------
        rl.begin_mode_3d(self.cam)

        # 1. Arena Stage (Double Layer Cyber Cylinder Podium)
        stage_pos = rl.Vector3(0.0, -0.06, 0.0)
        rl.draw_cylinder(stage_pos, 3.2, 3.4, 0.12, 40, rl.Color(24, 30, 44, 255))
        rl.draw_cylinder(rl.Vector3(0, 0.01, 0), 2.9, 2.9, 0.04, 40, rl.Color(36, 46, 68, 255))

        # Glowing Cyber Rings
        rl.draw_circle_3d(rl.Vector3(0, 0.032, 0), 2.85, rl.Vector3(1, 0, 0), 90.0, rl.Color(40, 180, 240, 220))
        rl.draw_circle_3d(rl.Vector3(0, 0.033, 0), 2.2, rl.Vector3(1, 0, 0), 90.0, rl.Color(60, 120, 200, 140))
        rl.draw_circle_3d(rl.Vector3(0, 0.034, 0), 1.2, rl.Vector3(1, 0, 0), 90.0, rl.Color(255, 180, 60, 120))

        # Ground Perspective Grid Lines
        for gx in range(-5, 6):
            rx = gx * 0.5
            rl.draw_line_3d(rl.Vector3(rx, 0.035, -2.5), rl.Vector3(rx, 0.035, 2.5), rl.Color(30, 50, 75, 120))
        for gz in range(-4, 5):
            rz = gz * 0.5
            rl.draw_line_3d(rl.Vector3(-2.6, 0.035, rz), rl.Vector3(2.6, 0.035, rz), rl.Color(30, 50, 75, 120))

        # 2. Four Neon Light Pillars at Stadium Corners
        pillar_coords = [(-2.8, -2.8), (2.8, -2.8), (-2.8, 2.8), (2.8, 2.8)]
        for px, pz in pillar_coords:
            rl.draw_cylinder(rl.Vector3(px, 0.9, pz), 0.08, 0.08, 1.8, 16, rl.Color(30, 42, 60, 255))
            rl.draw_sphere(rl.Vector3(px, 1.82, pz), 0.16, rl.Color(80, 220, 255, 220))

        # 3. Dynamic Distance Placement for Chimeras
        gap = 0.6 + self.engine.distance * 0.034
        pos_a = rl.Vector3(-gap * 0.5 + self.engine.a.anim_offset_x, 0.72 + self.engine.a.anim_offset_y, 0.0)
        pos_b = rl.Vector3(gap * 0.5 + self.engine.b.anim_offset_x, 0.72 + self.engine.b.anim_offset_y, 0.0)

        # Dynamic Drop Shadows
        shadow_a_rad = max(0.25, 0.55 - pos_a.y * 0.2)
        shadow_b_rad = max(0.25, 0.55 - pos_b.y * 0.2)
        rl.draw_circle_3d(rl.Vector3(pos_a.x, 0.038, 0.0), shadow_a_rad, rl.Vector3(1, 0, 0), 90.0, rl.Color(12, 16, 24, 180))
        rl.draw_circle_3d(rl.Vector3(pos_b.x, 0.038, 0.0), shadow_b_rad, rl.Vector3(1, 0, 0), 90.0, rl.Color(12, 16, 24, 180))

        # 4. Chimera 3D Voxel Models (Facing each other: A -> 90 deg, B -> -90 deg)
        rot_a = 90.0
        rot_b = -90.0
        if self.engine.a.fstate == FighterState.KO:
            rot_a = 90.0
        if self.engine.b.fstate == FighterState.KO:
            rot_b = -90.0

        self.model_a.draw(
            pos_a, scale=0.92, rot_y=rot_a, breathe=self.anim_t,
            squash_x=self.engine.a.squash_x, squash_y=self.engine.a.squash_y,
            rot_z=self.engine.a.rot_z if self.engine.a.fstate != FighterState.KO else 90.0
        )

        self.model_b.draw(
            pos_b, scale=0.92, rot_y=rot_b, breathe=self.anim_t,
            squash_x=self.engine.b.squash_x, squash_y=self.engine.b.squash_y,
            rot_z=self.engine.b.rot_z if self.engine.b.fstate != FighterState.KO else -90.0
        )

        rl.end_mode_3d()

        # ---------------------------------------------------------------------
        # 2D Arcade Battle HUD
        # ---------------------------------------------------------------------
        self._draw_battle_hud(w, h)

        # Countdown overlay
        if self.phase == TournamentPhase.COUNTDOWN:
            count_txt = str(int(math.ceil(self.phase_timer)))
            tw = rl.measure_text(count_txt, 80)
            rl.draw_rectangle(0, h // 2 - 70, w, 140, rl.Color(0, 0, 0, 190))
            rl.draw_text(count_txt, (w - tw) // 2, h // 2 - 45, 80, rl.Color(255, 220, 60, 255))
            ready_lbl = "READY FOR COMBAT"
            rw = rl.measure_text(ready_lbl, 18)
            rl.draw_text(ready_lbl, (w - rw) // 2, h // 2 + 40, 18, rl.WHITE)

        # Match Result overlay
        if self.phase == TournamentPhase.MATCH_RESULT:
            win_txt = f"{self.engine.winner.name.upper()} WINS !" if self.engine.winner else "DRAW !"
            tw = rl.measure_text(win_txt, 42)
            rl.draw_rectangle(0, h // 2 - 55, w, 110, rl.Color(0, 0, 0, 210))
            rl.draw_text(win_txt, (w - tw) // 2, h // 2 - 35, 42, rl.Color(255, 215, 60, 255))
            reason_txt = f"RESULT: {self.engine.end_reason}"
            rw = rl.measure_text(reason_txt, 16)
            rl.draw_text(reason_txt, (w - rw) // 2, h // 2 + 18, 16, rl.Color(190, 215, 240, 255))

    def _draw_battle_hud(self, w: int, h: int):
        # 1. Fighter A (Left / Player)
        rl.draw_text(self.engine.a.name, 40, 26, 20, rl.Color(80, 220, 240, 255))
        self._draw_hp_bar(40, 52, 400, 24, self.engine.a.hp, self.engine.a.max_hp)
        self._draw_guts_meter(40, 82, 400, 16, self.engine.a.guts)

        # 2. Fighter B (Right / Enemy)
        name_tw = rl.measure_text(self.engine.b.name, 20)
        rl.draw_text(self.engine.b.name, w - 40 - name_tw, 26, 20, rl.Color(255, 120, 140, 255))
        self._draw_hp_bar(w - 440, 52, 400, 24, self.engine.b.hp, self.engine.b.max_hp, flip=True)
        self._draw_guts_meter(w - 440, 82, 400, 16, self.engine.b.guts, flip=True)

        # 3. Center Digital Timer
        time_sec = int(math.ceil(self.engine.time_left))
        t_str = f"{time_sec:02d}"
        tw = rl.measure_text(t_str, 44)
        rl.draw_rectangle_rounded(rl.Rectangle(w // 2 - 60, 24, 120, 56), 0.25, 4, rl.Color(20, 26, 38, 240))
        rl.draw_rectangle_rounded_lines(rl.Rectangle(w // 2 - 60, 24, 120, 56), 0.25, 4, rl.Color(60, 80, 110, 255))
        time_col = rl.Color(255, 75, 75, 255) if time_sec <= 5 else rl.WHITE
        rl.draw_text(t_str, (w - tw) // 2, 30, 44, time_col)

        # 4. Floating Damage Popups (Projected from 3D to 2D Screen Space)
        for p in self.engine.popups:
            sp = rl.get_world_to_screen(rl.Vector3(p["x"], p["y"], 0.0), self.cam)
            tw = rl.measure_text(p["text"], 20)
            alpha_col = rl.Color(p["col"].r, p["col"].g, p["col"].b, int(min(1.0, p["life"]) * 255))
            rl.draw_text(p["text"], int(sp.x - tw / 2), int(sp.y), 20, alpha_col)

        # 5. Bottom Interactive Command Deck
        panel_y = h - 115
        rl.draw_rectangle(0, panel_y, w, 115, rl.Color(18, 24, 34, 245))
        rl.draw_line(0, panel_y, w, panel_y, rl.Color(42, 54, 74, 255))

        # Range Indicator Bar with Active Zone Color Coding
        dist_val = int(self.engine.distance)
        rl.draw_text(f"RANGE: {dist_val}m", 40, panel_y + 14, 14, rl.Color(180, 200, 220, 255))
        bar_x = 40
        bar_y = panel_y + 36
        bar_w = 240
        bar_h = 10
        rl.draw_rectangle(bar_x, bar_y, bar_w, bar_h, rl.Color(30, 38, 52, 255))

        # Colored Zone Bands (MELEE<=32 / BLAST>=30 オーバーラップ。デッドゾーン廃止)
        close_w = int(bar_w * 0.32)  # 0..32 Close Range (Strike)
        rl.draw_rectangle(bar_x, bar_y, close_w, bar_h, rl.Color(120, 60, 30, 180))
        long_x = bar_x + int(bar_w * 0.30)
        long_w = int(bar_w * 0.70)  # 30..100 Long Range (Blast)
        rl.draw_rectangle(long_x, bar_y, long_w, bar_h, rl.Color(30, 80, 120, 180))

        # Pointer Needle
        needle_x = bar_x + int((dist_val / 100.0) * bar_w)
        rl.draw_rectangle(needle_x - 3, bar_y - 3, 6, bar_h + 6, rl.Color(255, 225, 80, 255))

        # Zone Label (30-32は両方使えるミックスゾーン)
        zone_label = "[MIX ZONE]" if 30 <= dist_val <= 32 else ("[CLOSE RANGE]" if dist_val < 30 else "[LONG RANGE]")
        zone_col = rl.Color(180, 255, 140, 255) if 30 <= dist_val <= 32 else (rl.Color(255, 160, 60, 255) if dist_val < 30 else rl.Color(80, 200, 255, 255))
        rl.draw_text(zone_label, 140, panel_y + 14, 12, zone_col)

        # Move Guide text
        rl.draw_text("[A] / [D] : Dash Forward / Back", 40, panel_y + 60, 12, rl.Color(130, 145, 165, 255))

        # Action Cards (Mouse Clickable & Hotkey Enabled)
        can_melee = (self.engine.a.guts >= 15.0 and self.engine.distance <= 32.0)
        can_ranged = (self.engine.a.guts >= 25.0 and self.engine.distance >= 30.0)
        can_evade = (self.engine.a.guts >= 10.0)

        mouse_pos = rl.get_mouse_position()
        self._draw_action_card(
            self.btn_melee_card, "[J] STRIKE", "POW / GUTS 15 (CLOSE)",
            can_melee, rl.Color(255, 140, 50, 255), mouse_pos
        )
        self._draw_action_card(
            self.btn_ranged_card, "[K] BLAST", "INT / GUTS 25 (FAR)",
            can_ranged, rl.Color(80, 200, 255, 255), mouse_pos
        )
        self._draw_action_card(
            self.btn_evade_card, "[SPACE] EVADE", "DODGE / GUTS 10",
            can_evade, rl.Color(100, 240, 150, 255), mouse_pos
        )

        # Auto-Battle Toggle Card
        auto_hover = rl.check_collision_point_rec(mouse_pos, self.btn_auto_toggle)
        auto_bg = rl.Color(40, 65, 50, 255) if self.auto_battle else (rl.Color(40, 48, 62, 255) if auto_hover else rl.Color(28, 34, 46, 255))
        auto_border = rl.Color(80, 240, 140, 255) if self.auto_battle else rl.Color(60, 75, 95, 255)
        rl.draw_rectangle_rounded(self.btn_auto_toggle, 0.2, 4, auto_bg)
        rl.draw_rectangle_rounded_lines(self.btn_auto_toggle, 0.2, 4, auto_border)

        auto_str = "[TAB] AUTO: ON" if self.auto_battle else "[TAB] AUTO: OFF"
        auto_col = rl.Color(80, 240, 140, 255) if self.auto_battle else rl.Color(160, 175, 195, 255)
        rl.draw_text(auto_str, int(self.btn_auto_toggle.x + 14), int(self.btn_auto_toggle.y + 14), 14, auto_col)

    def _draw_hp_bar(self, x: int, y: int, bw: int, bh: int, hp: int, max_hp: int, flip: bool = False):
        ratio = max(0.0, min(1.0, hp / max(1, max_hp)))
        rl.draw_rectangle(x, y, bw, bh, rl.Color(28, 36, 48, 255))
        rl.draw_rectangle_lines(x, y, bw, bh, rl.Color(55, 70, 92, 255))

        bar_col = rl.Color(80, 220, 120, 255) if ratio > 0.5 else (rl.Color(255, 200, 50, 255) if ratio > 0.2 else rl.Color(255, 65, 65, 255))
        fill_w = int(bw * ratio)
        fill_x = x if not flip else (x + bw - fill_w)
        rl.draw_rectangle(fill_x, y, fill_w, bh, bar_col)

        hp_txt = f"HP  {hp} / {max_hp}"
        tw = rl.measure_text(hp_txt, 13)
        rl.draw_text(hp_txt, x + (bw - tw) // 2, y + 5, 13, rl.WHITE)

    def _draw_guts_meter(self, x: int, y: int, bw: int, bh: int, guts: float, flip: bool = False):
        ratio = max(0.0, min(1.0, guts / 99.0))
        rl.draw_rectangle(x, y, bw, bh, rl.Color(20, 26, 36, 255))
        rl.draw_rectangle_lines(x, y, bw, bh, rl.Color(45, 55, 75, 255))

        fill_w = int(bw * ratio)
        fill_x = x if not flip else (x + bw - fill_w)
        rl.draw_rectangle(fill_x, y, fill_w, bh, rl.Color(255, 180, 50, 255))

        txt = f"GUTS  {int(guts)}"
        rl.draw_text(txt, x + 8 if not flip else (x + bw - 70), y + 2, 11, rl.WHITE)

    def _draw_action_card(
        self, rec: rl.Rectangle, title: str, sub: str,
        enabled: bool, acc_col: rl.Color, mouse_pos: rl.Vector2
    ):
        hover = rl.check_collision_point_rec(mouse_pos, rec)
        if enabled:
            bg = rl.Color(42, 54, 76, 255) if hover else rl.Color(30, 38, 54, 255)
            border = rl.Color(255, 255, 255, 255) if hover else acc_col
            txt_col = rl.WHITE
        else:
            bg = rl.Color(20, 25, 34, 200)
            border = rl.Color(42, 50, 66, 255)
            txt_col = rl.Color(90, 105, 125, 255)

        rl.draw_rectangle_rounded(rec, 0.15, 4, bg)
        rl.draw_rectangle_rounded_lines(rec, 0.15, 4, border)
        rl.draw_text(title, int(rec.x + 12), int(rec.y + 14), 16, txt_col)
        rl.draw_text(sub, int(rec.x + 12), int(rec.y + 42), 11, rl.Color(160, 175, 195, 255) if enabled else rl.Color(70, 80, 95, 255))

    # -------------------------------------------------------------------------
    # Victory & Award Ceremony Screen
    # -------------------------------------------------------------------------
    def _draw_victory_screen(self, w: int, h: int):
        rl.clear_background(rl.Color(14, 18, 26, 255))

        if self.mgr.player_won:
            rl.draw_text("★ TOURNAMENT CHAMPION ★", w // 2 - 270, 100, 36, rl.Color(255, 215, 0, 255))
            congrats_txt = f"CONGRATULATIONS! {self.mgr.my_fighter.name.upper()} CONQUERED THE ARENA!"
            cw = rl.measure_text(congrats_txt, 16)
            rl.draw_text(congrats_txt, (w - cw) // 2, 160, 16, rl.Color(230, 240, 255, 255))
        else:
            rl.draw_text("TOURNAMENT CONCLUDED", w // 2 - 240, 100, 36, rl.Color(160, 180, 210, 255))
            champ_name = self.mgr.champion.name.upper() if self.mgr.champion else "UNKNOWN"
            champ_txt = f"ARENA CHAMPION: {champ_name}"
            cw = rl.measure_text(champ_txt, 18)
            rl.draw_text(champ_txt, (w - cw) // 2, 160, 18, rl.Color(255, 200, 80, 255))

        # Hardware Fatigue Feedback Box
        el, hg, win = self.mgr.compute_fatigue_payload()
        box_rec = rl.Rectangle(w // 2 - 270, 220, 540, 160)
        rl.draw_rectangle_rounded(box_rec, 0.08, 4, rl.Color(24, 32, 46, 255))
        rl.draw_rectangle_rounded_lines(box_rec, 0.08, 4, rl.Color(60, 85, 120, 255))

        rl.draw_text("HARDWARE FEEDBACK TRANSMITTED", int(box_rec.x + 24), int(box_rec.y + 20), 14, rl.Color(80, 220, 240, 255))
        rl.draw_text(f"Serial Command: TOURNEY {el} {hg} {win}", int(box_rec.x + 24), int(box_rec.y + 50), 13, rl.Color(190, 210, 230, 255))
        rl.draw_text(f"Energy Consumed: -{el}    Hunger Gained: +{hg}", int(box_rec.x + 24), int(box_rec.y + 80), 14, rl.Color(255, 185, 75, 255))
        rl.draw_text("E-Ink Display: Set FATIGUE expression & Sleep cycle", int(box_rec.x + 24), int(box_rec.y + 115), 12, rl.Color(140, 160, 180, 255))

        # Return to Farm Button
        mouse_pos = rl.get_mouse_position()
        hover = rl.check_collision_point_rec(mouse_pos, self.btn_return_farm)
        btn_bg = rl.Color(50, 75, 110, 255) if hover else rl.Color(34, 48, 70, 255)
        rl.draw_rectangle_rounded(self.btn_return_farm, 0.25, 4, btn_bg)
        rl.draw_rectangle_rounded_lines(self.btn_return_farm, 0.25, 4, rl.Color(255, 215, 0, 255) if hover else rl.Color(80, 220, 240, 255))

        ret_lbl = ">> RETURN TO TERRARIUM <<"
        tw = rl.measure_text(ret_lbl, 16)
        tx = int(self.btn_return_farm.x + (self.btn_return_farm.width - tw) / 2)
        ty = int(self.btn_return_farm.y + 18)
        rl.draw_text(ret_lbl, tx, ty, 16, rl.Color(255, 220, 60, 255) if hover else rl.WHITE)
