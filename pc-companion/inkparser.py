# pc-companion/inkparser.py
"""
InkLife シリアルプロトコル解析 & 状態モデル
ファームウェアが出力する +LIFE, +EVT, +BORN, +EVOLVE, +INSPECT, +TEST,
+AFF, +FZ, +FIELD, +CARE 等の行を解析し、
内部のキメラ状態・知人帳・現象盤ログをリアルタイムに更新します。
"""

import re
from typing import Dict, List, Optional, Any, Tuple

# 形態マップ (FW screen.h 準拠)
# ANCHOR_BASE_MAP が装備アンカー & fuse優劣の正規マップ (実機正)。
# 旧MORPH_5_MAPはFW削除に追随し撤去済み (値が異なり使用禁止だったもの)。
ANCHOR_BASE_MAP = [0, 1, 2, 1, 4, 2, 1, 7, 0, 4, 10, 0]  # FW ANCHOR_BASE_MAP そのまま

# 成長段階の境界 (FW life/evo.h と1:1。ここが唯一の定義元でPC各所はこれを参照する)
EGG_AGE_MAX = 300     # 未満はタマゴ
LARVA_AGE_MAX = 1800  # 未満は幼生。以上で成体 (=進化判定点)
GROWTH_SEC_PER_PX = 60  # FW growthSize: 64px + age/60 → 96px (旧270)

# 進化テーブル (FW life/evo.h EVO_TABLE と1:1)。[rank][trait] -> morph
# rank 0=S 1=A 2=B 3=C / trait 0=INT 1=AGGR 2=CURIO 3=SOC
EVO_TABLE = [
    [5, 1, 10, 2],
    [8, 4, 6, 7],
    [0, 9, 11, 0],
    [3, 3, 9, 3],
]
EVO_RANK_NAMES = "SABC"
EVO_TRAIT_ORDER = ["INT", "AGGR", "CURIO", "SOC"]
MORPH_NAMES = {0: "SLIME", 1: "DRAGON", 2: "SHIBA", 3: "SPINE", 4: "CAT", 5: "HALO", 6: "FIN", 7: "FROG", 8: "SPIRAL", 9: "LEG", 10: "WHISKER", 11: "STAR"}
GEAR_NAMES = [
    "まる", "つの", "みみ", "とげ", "しま", "わっか",
    "ひれ", "おうかん", "うず", "あし", "ひげ", "ほし"
]
GEAR_NAMES_EN = [
    "Orb", "Horns", "Ears", "Spikes", "Stripes", "Halo",
    "Fin", "Crown", "Swirl", "Legs", "Whiskers", "Star"
]

# 各形態のMF2トレーニング適性 [0]=最得意(A), [1]=第2適性(B) (0:INT, 1:AGGR, 2:CURIO, 3:SOC)
MORPH_TRAIT_APTITUDE = [
    (0, 3),  # 0: まる (スライム)   -> INT, SOC
    (1, 2),  # 1: つの (ちびドラ)   -> AGGR, CURIO
    (3, 0),  # 2: みみ (柴犬)       -> SOC, INT
    (1, 2),  # 3: とげ (トゲドラ)   -> AGGR, CURIO
    (2, 1),  # 4: しま (トラ猫)     -> CURIO, AGGR
    (0, 2),  # 5: わっか (フクロウ) -> INT, CURIO
    (2, 3),  # 6: ひれ (お魚)       -> CURIO, SOC
    (3, 0),  # 7: おうかん (カエル) -> SOC, INT
    (0, 3),  # 8: うず (カタツムリ) -> INT, SOC
    (1, 0),  # 9: あし (ゴーレム)   -> AGGR, INT
    (0, 2),  # 10: ひげ (狐)        -> INT, CURIO
    (3, 2),  # 11: ほし (サンショウ)-> SOC, CURIO
]

def hab_gain(base: int, exposure: int) -> int:
    """FW creature.h habGain と同一式 (PC楽観更新の同期用)。"""
    m = 100 - exposure
    if m < 20:
        m = 20
    return (base * m + 50) // 100

def stat_rank(val: int) -> str:
    """MF2風の能力値ランク (E..S)"""
    if val >= 85: return "S"
    if val >= 70: return "A"
    if val >= 55: return "B"
    if val >= 40: return "C"
    if val >= 25: return "D"
    return "E"

def condition_label(energy: int, health: int, happiness: int) -> Tuple[str, str]:
    """MF2風のモンスター体調・コンディション (ラベル, カラーキー)"""
    if energy < 15 or health < 25:
        return ("COLLAPSE WARNING!", "DANGER")
    if energy < 35:
        return ("EXHAUSTED", "WARN")
    if energy >= 70 and happiness >= 75:
        return ("PEAK FORM !!", "PEAK")
    if energy >= 50 and happiness >= 50:
        return ("GREAT", "GOOD")
    return ("NORMAL", "NORMAL")

def zone_of(gear_id: int) -> int:
    """部位ゾーン: 0=HEAD, 1=BACK, 2=BELLY, 3=AURA"""
    if gear_id in (1, 2, 7):
        return 0  # HEAD
    if gear_id in (3, 6, 9):
        return 1  # BACK
    if gear_id in (4, 8, 10):
        return 2  # BELLY
    return 3      # AURA (0, 5, 11)

def base_morph_of(species_id: int) -> int:
    # FW screen.h sprite() と同一: ANCHOR_BASE_MAP[raw] を使う
    return ANCHOR_BASE_MAP[species_id % 12]

# 睡眠時HEAD追従オフセット (dx, dy)。FW screen.h SLEEP_HEAD_OFF と1:1同期。
# 睡眠絵では頭が動くため、HEAD装備のアンカーに加算する。mid順 {0,1,2,4,7,10}。
SLEEP_HEAD_MIDS = (0, 1, 2, 4, 7, 10)
SLEEP_HEAD_OFF = [(0, 10), (-4, 10), (0, 5), (-6, 16), (0, 14), (-2, 5)]

def sleep_head_off(mid: int):
    """睡眠時HEADオフセット (dx, dy)。FW headMidIndexと同一 (未知midは狐に倒す)"""
    try:
        return SLEEP_HEAD_OFF[SLEEP_HEAD_MIDS.index(mid)]
    except ValueError:
        return SLEEP_HEAD_OFF[5]

def normalize_action(action: str) -> str:
    """FWのシリアル表記 (STANDBY/FEED/UPLINK/...) をPC内部名に正規化。
    E-Ink表示は生文字列のままが実機正だが、アート解決・AI判定は正規化後を使う。
    """
    a = (action or "").upper()
    if a == "STANDBY":
        return "IDLE"
    if a == "FEED":
        return "EAT"
    if a == "UPLINK":
        return "COMM"
    if a == "SURVEY":
        return "EXPLORE"
    if a == "FORAGE":
        return "SEEK"
    if a == "EVADE":
        return "FLEE"
    if a == "COMBAT":
        return "FIGHT"
    return a

# FW trait名 (INT/AGGR/CURIO/SOC) -> PC表示名 (INT/POW/SPD/SKI)
FW_STAT_TO_DISPLAY = {"INT": "INT", "AGGR": "POW", "CURIO": "SPD", "SOC": "SKI"}
DISPLAY_TO_FW_STAT = {"INT": "INT", "POW": "AGGR", "SPD": "CURIO", "SKI": "SOC"}

def fuse_shown_gears(fuse_list: List[int], mid: int, raw: Optional[int] = None) -> List[int]:
    """実際に有効なパーツID一覧をFW描画順 (奥→手前: AURA→BACK→BELLY→HEAD) で返す。
    適用則 (FW screen.hと同一): 同部位優劣・自前スキップ・重複スキップ、
    頭頂競合 (ハローは王冠・角と重なるため両者表示時は譲る。遺伝子は保持)"""
    shown = []
    won_mask = 0
    for f in fuse_list[:4]:
        if f is None or f > 11 or f == mid or (raw is not None and f == raw):
            continue
        if f in shown:
            continue
        z = zone_of(f)
        if won_mask & (1 << z):
            continue
        won_mask |= (1 << z)
        shown.append(f)
    if 5 in shown and (7 in shown or 1 in shown):
        shown.remove(5)  # ハロー譲歩
    shown.sort(key=lambda g: (3, 1, 2, 0).index(zone_of(g)))
    return shown

# イベント発生時のセリフ集 (Raylib 標準フォントで化けない ASCII 英語表記)
EVENT_SPEECH = {
    "FEED_OK": "*nom nom* Delicious!",
    "PLAY_OK": "Yay! Having so much fun!",
    "STUFFED": "Full and happy...",
    "LOW_ENERGY": "Tired... need sleep...",
    "ENTER_REST": "Zzz... Good night...",
    "FEED_START": "Snack time!",
    "PLAY_START": "Let's play!",
    "SURVEY_START": "Scanning the radio waves...",
    "SCAN_SIGNAL": "LoRa signal detected!",
    "STANDBY": "Observing the digital sky...",
    "WAKE_OK": "System Online! Ready!",
    "BIRTH_OK": "Hello World! Chimera born!",
    "GENESIS": "Genesis sequence complete!",
    "ALLY_RX": "Kin friend signal detected!",
    "GREET_RX": "Hello! Packet received!",
    "STRANGER_RX": "Unknown signal nearby...",
    "FOOD_RX": "Received a treat! Thanks!",
    "TR:GREAT!": "GREAT SUCCESS! Power surges through me!",
    "TR:SUCCESS": "Training complete! Growing stronger!",
    "TR:FAIL": "Oops... couldn't make it this time...",
    "TR:SLACK": "Hehe, played hooky today~",
    "OVERWORK": "Too exhausted... need rest badly...",
    "FOOD_TX": "Shared food packet sent!",
    "PLAY_RX": "Playing with peer in mesh!",
    "FATIGUE": "Energy depleted...",
    "COMBAT_WIN": "Victory in duel!",
    "COMBAT_LOSS": "Ouch... Defeated...",
    "TRADE_OK": "Gene exchange complete!",
    "TRADE_REFUSE": "Trade declined...",
    "BIRTH_RX": "New life born in mesh network!",
    "GETWELL_RX": "Healing wave received!",
    "SLEEP_RX": "Peer is resting too...",
    "PEER_FOUND": "New peer chimera discovered!",
    "BONDED": "Bonded as best friends!",
    "RIVAL": "Rival detected!",
    "NIGHTFALL": "Night cycle begins...",
    "DAYBREAK": "Morning! Sunlight charging...",
    "DEAD": "Reincarnating to next Gen...",
    "STAY": "PC Link Active (Always-On)",
    "EVOLVE": "Evolution! New form!",
    "EVOLVE_RX": "Peer evolved! Congrats!",
    "OHAYO": "Good morning! *chirp*",
    "CLEAN_OK": "*scrub scrub* All clean!",
    "SPOTLESS": "Already spotless!",
    "CURE_OK": "Medicine taken... feeling better!",
    "NO_NEED": "Healthy! No medicine needed.",
    "TR:PERFECT!": "PERFECT!! Crown earned!",
    "TR:FLYING": "Oops... jumped the gun...",
    "TEST_START": "Reaction test... steady...",
}

class PeerInfo:
    def __init__(self, did: str, aff: int = 0, known: bool = True, species: int = 0, rssi: int = -70):
        self.did = did
        self.aff = aff
        self.known = known
        self.species = species
        self.rssi = rssi
        self.fuse: List[int] = [255, 255, 255, 255]  # FW知人帳fz (v3 STATUS)

class CreatureState:
    def __init__(self):
        self.age_sec: int = 0
        self.health: int = 90
        self.hunger: int = 20
        self.energy: int = 90
        self.happiness: int = 70
        self.cleanliness: int = 80
        self.action: str = "IDLE"
        self.generation: int = 1
        self.intelligence: int = 50
        self.curiosity: int = 50
        self.aggression: int = 50
        self.sociability: int = 50
        self.species_id: int = 1  # 既定: ドラゴン (つの)
        self.fuse: List[int] = [255, 255, 255, 255]
        self.habit: List[int] = [0, 0, 0]  # [FOOD, PLAY, SOCIAL]
        self.last_event: str = "GENESIS"
        self.speech_bubble: str = "InkLife 起動中…"
        self.speech_timer: float = 4.0
        self.device_id: int = 0xABCD1234

        # 知人帳
        self.peers: Dict[str, PeerInfo] = {}

        # 現象盤情報
        self.field_hash: int = 0
        self.field_activity: int = 120
        self.field_symmetry: int = 8
        self.field_grid: List[List[int]] = [[0] * 48 for _ in range(12)]  # FIELDB実盤面
        self.field_seq: int = 0  # 盤面更新カウンタ (再描画ゲート用)

        # 感情計算 (SICK, SLEEPY, SAD, HAPPY, NORMAL)
        self.mood: str = "NORMAL"

        # 初回+LIFE受信済みか (接続直後のデモ値＋生ID混在の Frankenstein 表示防止用)
        self.has_life: bool = False

    def update_mood(self):
        if self.health < 30:
            self.mood = "SICK"
        elif self.action == "SLEEP" or self.energy < 15:
            self.mood = "SLEEPY"
        elif self.hunger > 70 or self.happiness < 30:
            self.mood = "SAD"
        elif self.happiness > 60 and self.hunger < 50:
            self.mood = "HAPPY"
        else:
            self.mood = "NORMAL"

    @property
    def raw_morph(self) -> int:
        return self.species_id % 12

    @property
    def base_mid(self) -> int:
        return base_morph_of(self.species_id)

    @property
    def base_name(self) -> str:
        return MORPH_NAMES.get(self.raw_morph, "CHIMERA")

    @property
    def stage_name(self) -> str:
        if self.age_sec < EGG_AGE_MAX:
            return "EGG"
        if self.age_sec < LARVA_AGE_MAX:
            return "JUV"
        if self.age_sec < 43200:
            return "ADULT"
        return "ELDER"

    @property
    def effective_gears(self) -> List[int]:
        return fuse_shown_gears(self.fuse, self.base_mid, self.raw_morph)

class InkProtocolParser:
    RE_LIFE = re.compile(r"^\+LIFE age=(\d+) hp=(\d+) hu=(\d+) en=(\d+) ha=(\d+) act=([A-Z]+) gen=(\d+) tr=(\d+),(\d+),(\d+),(\d+)")
    RE_EVT = re.compile(r"^\+EVT ?(.*)$")
    RE_BORN = re.compile(r"^\+BORN gen=(\d+) mate=(\w+) tr=([\d,]+) sp=(\d+) fz=([\d,]+)")
    RE_FZ = re.compile(r"^\+FZ (\d+),(\d+),(\d+),(\d+)")
    RE_SP = re.compile(r"^\+SP (\d+)$")
    RE_ID = re.compile(r"^\+ID ([0-9A-Fa-f]+)$")
    RE_FIELDB = re.compile(r"^\+FIELDB (\d+) ([0-9a-fA-F]{24})$")
    RE_AFF_N = re.compile(r"^\+AFF n=(\d+)")
    RE_AFF_PEER = re.compile(r"^\+AFF ([0-9A-Fa-f]+) aff=(-?\d+) (known|strange)")
    RE_AFF_HABIT = re.compile(r"^\+AFF habit=(\d+),(\d+),(\d+)")
    RE_FIELD = re.compile(r"^\+FIELD (?:sym=(\d+) act=(\d+) bias=(-?\d+)|hash=([0-9A-Fa-f]+) act=(\d+) sym=(\d+))")
    RE_HEARD = re.compile(r"^\+HEARD did=([0-9A-Fa-f]+) type=(\w+)(?: rssi=(-?[\d\.]+))?")
    RE_RESTORED = re.compile(r"^\+RESTORED src=(\w+) absence=(\d+) boots=(\d+)")
    RE_TRAIN = re.compile(r"^\+TRAIN res=(\w+)(?: stat=(\w+) gain=(\d+))?(?: hp=(\d+))?(?: en=(\d+))?(?: ha=(\d+))?")
    RE_EVOLVE = re.compile(r"^\+EVOLVE (\d+)->(\d+) rank=([SABC]) score=(-?\d+) g=(\d+) m=(\d+) ow=(\d+) bond=(-?\d+) riv=(-?\d+)")
    RE_INSPECT = re.compile(r"^\+INSPECT target=(\w+) grade=(\d+) dt=(-?\d+)")
    RE_TEST = re.compile(r"^\+TEST (3|2|1|GO!!)$")

    def __init__(self, state: CreatureState):
        self.state = state

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or not line.startswith("+"):
            return None

        # +LIFE
        m = self.RE_LIFE.match(line)
        if m:
            self.state.age_sec = int(m.group(1))
            self.state.health = int(m.group(2))
            self.state.hunger = int(m.group(3))
            self.state.energy = int(m.group(4))
            self.state.happiness = int(m.group(5))
            self.state.action = m.group(6)
            self.state.generation = int(m.group(7))
            self.state.intelligence = int(m.group(8))
            self.state.curiosity = int(m.group(9))
            self.state.aggression = int(m.group(10))
            self.state.sociability = int(m.group(11))
            self.state.has_life = True
            self.state.update_mood()
            return {"type": "life"}

        # +TRAIN (FWは res/stat/gain に加え hp/en/ha を付与する。即時反映しないと30秒ズレる)
        m = self.RE_TRAIN.match(line)
        if m:
            res = m.group(1)
            stat = m.group(2)
            gain = int(m.group(3)) if m.group(3) else 0
            if stat and gain > 0:
                if stat == "INT": self.state.intelligence = min(100, self.state.intelligence + gain)
                elif stat == "AGGR": self.state.aggression = min(100, self.state.aggression + gain)
                elif stat == "CURIO": self.state.curiosity = min(100, self.state.curiosity + gain)
                elif stat == "SOC": self.state.sociability = min(100, self.state.sociability + gain)
            # FW付随値の即時反映 (欠落時は無視)
            if m.group(4):
                self.state.health = max(1, min(100, int(m.group(4))))
            if m.group(5):
                self.state.energy = max(0, min(100, int(m.group(5))))
            if m.group(6):
                self.state.happiness = max(0, min(100, int(m.group(6))))
            disp_stat = FW_STAT_TO_DISPLAY.get(stat, stat) if stat else stat
            return {"type": "train", "res": res, "stat": disp_stat, "fw_stat": stat, "gain": gain}

        # +EVT
        m = self.RE_EVT.match(line)
        if m:
            evt = m.group(1).strip()
            self.state.last_event = evt
            if evt in EVENT_SPEECH:
                self.state.speech_bubble = EVENT_SPEECH[evt]
                self.state.speech_timer = 4.0
            return {"type": "event", "event": evt}

        # +BORN (形質trも即時反映。+LIFE待ちだと30秒スライム/旧能力のまま)
        m = self.RE_BORN.match(line)
        if m:
            self.state.generation = int(m.group(1))
            try:
                tr_vals = [int(x) for x in m.group(3).split(",")]
                if len(tr_vals) >= 4:
                    self.state.intelligence = max(0, min(100, tr_vals[0]))
                    self.state.curiosity = max(0, min(100, tr_vals[1]))
                    self.state.aggression = max(0, min(100, tr_vals[2]))
                    self.state.sociability = max(0, min(100, tr_vals[3]))
            except ValueError:
                pass
            self.state.species_id = int(m.group(4))
            fz = [int(x) for x in m.group(5).split(",")]
            self.state.fuse = (fz + [255] * 4)[:4]
            # FW doRebirthと同一の新生値 (+LIFEまでの30秒が生まれたてに見えるよう)
            self.state.age_sec = 0
            self.state.health = 90
            self.state.hunger = 20
            self.state.energy = 90
            self.state.happiness = 70
            self.state.cleanliness = 80
            self.state.habit = [0, 0, 0]
            self.state.speech_bubble = f"Reborn as Gen {self.state.generation} Chimera!"
            self.state.speech_timer = 5.0
            self.state.update_mood()
            return {"type": "born"}

        # +EVOLVE (形態のみ上書き。血統variant維持はFW側で済み。+LIFE待ちだと旧姿のまま)
        m = self.RE_EVOLVE.match(line)
        if m:
            after = int(m.group(2))
            if 0 <= after <= 11:
                self.state.species_id = self.state.species_id - (self.state.species_id % 12) + after
            self.state.speech_bubble = f"Evolution! Rank {m.group(3)}!"
            self.state.speech_timer = 5.0
            self.state.update_mood()
            return {"type": "evolve", "before": int(m.group(1)), "after": after,
                    "rank": m.group(3), "score": int(m.group(4))}

        # +INSPECT (PC検査・FW検査の結果。カットインは呼出側)
        m = self.RE_INSPECT.match(line)
        if m:
            return {"type": "inspect", "target": m.group(1), "grade": int(m.group(2)),
                    "dt": int(m.group(3))}

        # +TEST (検査カウントダウン・GO合図。PCゲーム同期用)
        m = self.RE_TEST.match(line)
        if m:
            mark = m.group(1)
            self.state.speech_bubble = "GO!! Press BOOT!" if mark == "GO!!" else f"{mark}..."
            self.state.speech_timer = 2.0
            return {"type": "test", "mark": mark}

        # +FZ
        m = self.RE_FZ.match(line)
        if m:
            self.state.fuse = [int(m.group(i)) for i in range(1, 5)]
            return {"type": "fuse"}

        # +SP (種番号。接続直後に問い合わせること)
        m = self.RE_SP.match(line)
        if m:
            self.state.species_id = int(m.group(1))
            return {"type": "species"}

        # +ID (個体ID HEX8。E-InkのID行同期用)
        m = self.RE_ID.match(line)
        if m:
            try:
                self.state.device_id = int(m.group(1), 16) & 0xFFFFFFFF
            except ValueError:
                pass
            return {"type": "device_id"}

        # +FIELDB <row> <24hex> (2bit/cell packing。FWのFIELDBと対応)
        m = self.RE_FIELDB.match(line)
        if m:
            row = int(m.group(1))
            if 0 <= row < 12:
                raw = bytes.fromhex(m.group(2))
                cells = self.state.field_grid[row]
                for i, b in enumerate(raw[:12]):
                    for k in range(4):
                        x = i * 4 + k
                        if x < 48:
                            cells[x] = (b >> (k * 2)) & 3
                self.state.field_seq += 1
                return {"type": "fieldb", "row": row}
            return {"type": "other", "raw": line}

        # +AFF n=
        m = self.RE_AFF_N.match(line)
        if m:
            return {"type": "aff_n", "n": int(m.group(1))}

        # +AFF <did> aff=... (末尾の fz=.. はv3融合遺伝子。無ければ欠落扱い)
        m = self.RE_AFF_PEER.match(line)
        if m:
            did = m.group(1).upper()
            aff = int(m.group(2))
            known = m.group(3) == "known"
            fz_m = re.search(r"fz=(\d+),(\d+),(\d+),(\d+)", line)
            fz = [int(fz_m.group(i)) for i in range(1, 5)] if fz_m else None
            if did in self.state.peers:
                self.state.peers[did].aff = aff
                self.state.peers[did].known = known
                if fz is not None:
                    self.state.peers[did].fuse = fz
            else:
                peer = PeerInfo(did, aff, known)
                if fz is not None:
                    peer.fuse = fz
                self.state.peers[did] = peer
            return {"type": "aff_peer", "did": did}

        # +AFF habit=
        m = self.RE_AFF_HABIT.match(line)
        if m:
            self.state.habit = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
            return {"type": "habit"}

        # +FIELD
        m = self.RE_FIELD.match(line)
        if m:
            if m.group(1) is not None:
                self.state.field_symmetry = int(m.group(1))
                self.state.field_activity = int(m.group(2))
            else:
                self.state.field_activity = int(m.group(5))
                self.state.field_symmetry = int(m.group(6))
            return {"type": "field"}

        # +HEARD
        m = self.RE_HEARD.match(line)
        if m:
            did = m.group(1).upper()
            pkt_type = m.group(2)
            rssi = float(m.group(3)) if m.group(3) else -60.0
            if did not in self.state.peers:
                self.state.peers[did] = PeerInfo(did, 0, False, rssi=int(rssi))
            else:
                self.state.peers[did].rssi = int(rssi)
            return {"type": "heard", "did": did, "packet": pkt_type}

        return {"type": "other", "raw": line}
