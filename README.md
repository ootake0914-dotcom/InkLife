# InkLife — Autonomous E-Ink & LoRa Artificial Life

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hardware](https://img.shields.io/badge/Hardware-Heltec_Vision_Master_E290-blue.svg)](https://heltec.org/)
[![MCU](https://img.shields.io/badge/MCU-ESP32--S3R8_Dual--Core-red.svg)]()
[![Display](https://img.shields.io/badge/Display-2.9%22_E--Ink_296x128-black.svg)]()
[![Radio](https://img.shields.io/badge/Radio-SX1262_LoRa_923MHz-orange.svg)]()

**InkLife** is a decentralized artificial lifeform living on an ultra-low-power electronic paper habitat, specifically engineered for the **Heltec Vision Master E290** development platform. Creatures live calmly on their bistable display, autonomously encounter peer devices over long-range **LoRa mesh networks**, form relationships, trade nutrients, battle, and cross-breed across generations—completely free of Wi-Fi, cloud servers, or smartphone dependencies.

Featuring an asymmetric dual-core architecture, a strict 48-byte packed genetic memory model, an ambient cellular automaton ("Phenomenon Field"), and a *Monster Farm 2*-inspired training engine with exhaustion mechanics.

<p align="center">
  <img src="docs/pc_companion_station.png" width="850" alt="InkLife 3D Companion Station & Virtual E-Ink Mirror"/>
</p>

---

## Visual Showcase — 12 Distinct Species

All 12 distinct forms feature dedicated 1-bit pixel art across 5 core emotional actions (`IDLE`, `SLEEP`, `EAT`, `HAPPY`, `SAD`), totaling 60 hand-crafted frames with dynamic 4-zone chimera fusion:

| ID | Species Name | Archetype | Dominant Aptitude | Preview |
| :---: | :--- | :--- | :--- | :---: |
| **0** | **Maru** (まる) | Slime / Amoeba | Intelligence (かしこさ) | <img src="assets/ink_m00_idle.jpg" width="80" alt="Maru"/> |
| **1** | **Tsuno** (つの) | Horned Drake | Aggression (ちから) | <img src="assets/ink_m01_idle.jpg" width="80" alt="Tsuno"/> |
| **2** | **Mimi** (みみ) | Shiba Inu | Sociability (めいちゅう) | <img src="assets/ink_m02_idle.jpg" width="80" alt="Mimi"/> |
| **3** | **Toge** (とげ) | Spiked Drake | Aggression (ちから) | <img src="assets/ink_m03_idle.jpg" width="80" alt="Toge"/> |
| **4** | **Shima** (しま) | Tabby Cat | Curiosity (すばやさ) | <img src="assets/ink_m04_idle.jpg" width="80" alt="Shima"/> |
| **5** | **Wakka** (わっか) | Forest Owl | Intelligence (かしこさ) | <img src="assets/ink_m05_idle.jpg" width="80" alt="Wakka"/> |
| **6** | **Hire** (ひれ) | Aquatic Fin | Curiosity (すばやさ) | <img src="assets/ink_m06_idle.jpg" width="80" alt="Hire"/> |
| **7** | **Oukan** (おうかん) | Frog Prince | Sociability (めいちゅう) | <img src="assets/ink_m07_idle.jpg" width="80" alt="Oukan"/> |
| **8** | **Kora** (こうら) | Armored Snail | Intelligence (かしこさ) | <img src="assets/ink_m08_idle.jpg" width="80" alt="Kora"/> |
| **9** | **Iwa** (いわ) | Stone Golem | Aggression (ちから) | <img src="assets/ink_m09_idle.jpg" width="80" alt="Iwa"/> |
| **10** | **Kitsune** (きつね) | Mystic Fox | Curiosity (すばやさ) | <img src="assets/ink_m10_idle.jpg" width="80" alt="Kitsune"/> |
| **11** | **Sanshou** (さんしょう) | Salamander | Sociability (めいちゅう) | <img src="assets/ink_m11_idle.jpg" width="80" alt="Sanshou"/> |

---

## Lifecycle & Care-Based Evolution (Egg → Larva → Adult → Elder)

InkLife creatures experience dynamic generational growth driven by care history, real-time internal clock, and evolutionary pressure:

```mermaid
flowchart LR
    EGG["🥚 EGG Stage<br/>(0 ~ 5 min)<br/>Crack & Hatch"] --> LARVA["🐛 LARVA Stage<br/>(5 ~ 30 min)<br/>Nourish & Train"]
    LARVA -->|"S-Rank Care<br/>(Care Score >= 15)"| S_MORPH["⭐ Elite Morphs<br/>(Tsuno, Mimi, Shima, Oukan)"]
    LARVA -->|"A-Rank Care<br/>(Care Score >= 5)"| A_MORPH["🌿 Standard Morphs<br/>(Maru, Wakka, Hire, Kitsune)"]
    LARVA -->|"B-Rank Care<br/>(Care Score < 5)"| B_MORPH["🪨 Neglect / Tough Morphs<br/>(Toge, Kora, Iwa, Sanshou)"]
    S_MORPH --> ELDER["👑 ELDER Stage (Age >= 12h)<br/>Sparkle Crown Mark"]
    A_MORPH --> ELDER
    B_MORPH --> ELDER
```

* **EGG (0 ~ 5 min)**: Smooth egg (`ink_egg_idle`) develops stress fractures (`ink_egg_crack` at 100s) and hatching eyes (`ink_egg_hatch` at 200s).
* **LARVA (5 ~ 30 min)**: Independent juvenile stage with 5 emotional expressions (`ink_larva_*`). Grows by +1px every 60s.
* **Branched Evolution (at 30 min)**: Evaluates cumulative care ledger:
  $$\text{CareScore} = (\text{GoodCare} \times 2) - (\text{CareMiss} \times 3) - (\text{Overwork} \times 2) - \text{NeglectTicks}$$
* **ELDER (Age >= 12h)**: Venerable lifeform status adorned with dual sparkle elder halos.

---

## Seasonal Hats & Expressive Overlays

Equip procedural and seasonal 1-bit overlays atop any species with pixel-perfect anchor alignment:

| Crown (`ink_crown`) | Pumpkin Hat (`ink_hat_pumpkin`) | Santa Hat (`ink_hat_santa`) | Kagami Mochi (`ink_hat_mochi`) | Droppings (`ink_poop_1/2`) |
| :---: | :---: | :---: | :---: | :---: |
| <img src="assets/ink_crown.jpg" width="90" alt="Crown"/> | <img src="assets/ink_hat_pumpkin.jpg" width="90" alt="Pumpkin Hat"/> | <img src="assets/ink_hat_santa.jpg" width="90" alt="Santa Hat"/> | <img src="assets/ink_hat_mochi.jpg" width="90" alt="Kagami Mochi"/> | <img src="assets/ink_poop_1.jpg" width="90" alt="Poop"/> |
| Tournament / Honor | Halloween Jack-o'-Lantern | Christmas Santa Trimming | New Year Double Mochi | Real-Time Excretion |

---

## System Architecture

The firmware utilizes an asymmetric FreeRTOS dual-core pipeline on the ESP32-S3, isolating heavy background cellular simulations and radio entropy generation from deterministic UI rendering and state-machine transitions:

```mermaid
flowchart TB
    subgraph HostPC ["Desktop Companion Station (Python 3.12 / Raylib)"]
        UI["Interactive 3D Voxel Terrarium<br/>Brian's Brain Hologram & Social Radar"]
        VINK["Virtual E-Ink Mirror (296x128 1-bit)"]
    end

    subgraph ESP32S3 ["Heltec Vision Master E290 (ESP32-S3R8 @ 240MHz)"]
        subgraph Core0 ["Core 0: Phenomenon & Entropy Worker"]
            BB["Brian's Brain 48x12 Cellular Automata<br/>(Ready -> Firing -> Refractory)"]
            ENT["Sub-GHz Radio Noise Pool<br/>Environmental Evolutionary Pressure"]
        end

        subgraph Core1 ["Core 1: Autonomous Life & UI Engine"]
            AI["Utility AI & State Machine<br/>(Idle, Sleep, Eat, Play, Train, Comm)"]
            MF2["MF2 Training & Overwork Servo<br/>(Dice Roll & Health Decay)"]
            GENE["4-Zone Chimera Inheritance<br/>(Head, Back, Belly, Aura)"]
        end

        subgraph Peripherals ["Hardware Interfaces"]
            LORA["Semtech SX1262 LoRa (923MHz)<br/>Decentralized Ad-hoc Mesh"]
            EINK["2.9\" Monochrome E-Ink (SSD1680)<br/>Fast Partial Refresh Driver (GxEPD2)"]
            NVS["Flash Storage (NVS)<br/>Strict 48-Byte State Persistence"]
        end
    end

    HostPC <== "USB-CDC Serial (115200 bps)<br/>Telemetry JSON & Host Commands" ==> ESP32S3
    Core0 -- "Environmental Pressure / CA Bias" --> Core1
    Core1 -- "Social Broadcast Packets" --> LORA
    LORA -- "Acquaintance Discovery" --> Core1
    Core1 -- "1-Bit Bitmaps + Fusion Anchors" --> EINK
    Core1 -- "Differential Checksum Save" --> NVS
```

---

## Low-Level Memory Architecture (48-Byte Packed Creature)

To maximize SPI flash write endurance, prevent NVS sector thrashing, and fit within ESP32-S3 L1 data cache lines, creature state is packed into **exactly 48 bytes**, strictly guaranteed at compile time via `static_assert(sizeof(Creature) == 48, ...)`:

```text
================================================================================
OFFSET  SIZE  FIELD              TYPE          DESCRIPTION
================================================================================
+0x00   4 B   id                 uint32_t      Unique Creature GUID (CRC32 seed)
+0x04   2 B   generation         uint16_t      Lineage Generation Counter
+0x06   1 B   morph_id           uint8_t       Base Species ID (0..11)
+0x07   1 B   flags              uint8_t       Bitflags (Sleeping, Sick, Exhausted)
+0x08   4 B   fusion_genes       Gene4Slot     4-Zone Chimera Slots (Head/Back/Belly/Aura)
+0x0C   1 B   hunger             uint8_t       Satiety Gauge (0..100)
+0x0D   1 B   energy             uint8_t       Vital Energy Gauge (0..100)
+0x0E   1 B   happiness          uint8_t       Emotional Valence (0..100)
+0x0F   1 B   health             uint8_t       Physical Integrity (0..100)
+0x10   4 B   aptitude           Stats4        MF2 Traits: Int / Aggr / Curio / Soc
+0x14   3 B   nature             Traits3       Personality: Patience, Sociability, Play
+0x17   1 B   reserved           uint8_t       Explicit 32-bit boundary alignment
+0x18   4 B   birth_time         uint32_t      RTC Epoch Timestamp (Birth)
+0x1C   4 B   last_update        uint32_t      RTC Epoch Timestamp (Last Processed Tick)
+0x20   4 B   exp_total          uint32_t      Cumulative Experience Points
+0x24   4 B   overwork_points    uint32_t      Cumulative Fatigue & Exhaustion Index
+0x28   8 B   social_summary     uint64_t      Top Acquaintance GUID Hash & Affinity
================================================================================
TOTAL SIZE: 48 BYTES (384 BITS) — ZERO HEAP ALLOCATION
```

---

## Technical Highlights

### 1. Decentralized LoRa Mesh Ecology
* **Zero Infrastructure**: Completely autonomous sub-GHz ad-hoc communications over the 923MHz band (Semtech SX1262).
* **Social Ledger**: Tracks up to 6 recognized neighboring devices with dynamic bidirectional affinity (-100 to +100). Sustained positive encounters establish `BONDED` pacts; territorial conflicts trigger `RIVAL` states.
* **Autonomous Interaction Protocol**:
  * `HELLO` / `STATUS`: Heartbeat telemetry and species announcement.
  * `GREET`: Affinity exchange and emotional synchronization.
  * `FOOD`: Emergency nutritional sharing (altruistic behavior).
  * `FIGHT` / `TRADE`: Competitive sparring and gene token exchanges.

### 2. Brian's Brain Cellular Automaton ("Phenomenon Field")
Core 0 runs an ambient 48×12 cellular automaton simulating primordial physical phenomena:
$$\text{State}(x, y, t+1) = 
\begin{cases} 
\text{Firing}, & \text{if State}(t) = \text{Ready and } \sum \text{Firing Neighbors} = 2 \\ 
\text{Refractory}, & \text{if State}(t) = \text{Firing} \\ 
\text{Ready}, & \text{if State}(t) = \text{Refractory} 
\end{cases}$$
Coupled with real-time RF noise entropy sampled from the SX1262 receiver, this field introduces genuine thermodynamic environmental pressure that drives mutation rates and behavioral whims.

### 3. Monster Farm 2-Inspired Training & Overwork Servo
Creatures can be trained to cultivate four primary genetic traits:
* **Intelligence (かしこさ)**: Increases curiosity and social communication success.
* **Aggression (ちから)**: Increases competitive dominance in territorial encounters.
* **Curiosity (すばやさ)**: Boosts exploration frequency and mutation chances.
* **Sociability (めいちゅう)**: Accelerates positive affinity accumulation over LoRa.

#### Aptitude & Dice-Roll Engine
Each species possesses innate aptitudes (Grade A through D). Training checks evaluate aptitude against a pseudo-random roll influenced by current happiness:
* **GREAT !** (+3~4 stat gain, visual joy emote)
* **SUCCESS** (+1~2 stat gain)
* **FAIL** (0 stat gain, stamina wasted)
* **SLACK** (Creature plays hooky, happiness boost, 0 stat gain)

#### Overwork & Health Decay Mechanics
Training consumes **20 Energy**. If training is forced when $\text{Energy} < 20$, an **OVERWORK** penalty triggers:
$$\text{OverworkRisk} = \frac{20 - \text{Energy}}{20} \times 100\%$$
Overwork inflicts severe health penalties, accumulates lifetime fatigue (`overwork_points`), and triggers the `SICK` mood with unique visual emotes.

---

## Hardware Specification

| Component | Specification | Pin Assignment / Interface |
| :--- | :--- | :--- |
| **Target Board** | **Heltec Vision Master E290** (All-in-One E-Paper + LoRa Development Board) | Dedicated Platform |
| **MCU** | ESP32-S3R8 (Dual-Core Xtensa LX7 @ 240MHz, 8MB PSRAM, 16MB Flash) | Embedded |
| **E-Ink Display** | 2.9" Monochrome E-Paper (296x128, SSD1680) | CS: 3, DC: 2, RST: 1, BUSY: 4, SPI |
| **LoRa Radio** | Semtech SX1262 Sub-GHz Transceiver (923MHz) | NSS: 8, RST: 5, BUSY: 13, DIO1: 14, SPI |
| **User Input** | Tactile Push Buttons | `BOOT` (GPIO 0), `SIDE` (GPIO 21) |
| **Serial Bus** | USB-CDC Hardware Virtual COM | 115200 bps, 8-N-1 |

---

## Controls & Interaction

### Physical Buttons
| Button | Input Type | Action | Description |
| :--- | :--- | :--- | :--- |
| **BOOT Button** | Short Click (< 0.5s) | **FEED** | Nourish creature (restores hunger, slight happiness boost) |
| **BOOT Button** | Long Press (> 1.2s) | **SHARE FOOD** | Broadcast emergency food nutrient packet over LoRa |
| **SIDE Button** | Short Click (< 0.5s) | **PLAY** | Interactive play (boosts happiness, consumes energy) |
| **SIDE Button** | Long Press (> 1.2s) | **TRAIN** | MF2-style dice training (morph-aptitude target, same economy as the PC TRAIN command) |
| **BOOT + SIDE** | Simultaneous Press | **CLEAN** | Clean droppings (restores cleanliness, small happiness boost) |

### Serial Command Interface (115200 bps)
```text
FEED                      # Feed creature immediately
PLAY                      # Play with creature
CLEAN                     # Clean droppings (serial/PC parallel to simultaneous press)
CURE                      # Administer medicine (serial/PC only, effective when sick)
TRAIN [INT|AGGR|CURIO|SOC]# Execute targeted or auto training (dice, automatic)
INSPECT <0..3>            # Apply PC-hosted minigame result (0:PERFECT..3:FAIL)
TIME <unix_timestamp>     # Synchronize system RTC with host PC (drives JST day/night AI & morning bonus)
SP                        # Query species and morph metadata
FZ                        # Query 4-zone equipped chimera genes
AFF                       # Print social acquaintance ledger & affinities
CARE                      # Print care counters & evolution score breakdown
BENCH                     # Benchmark sprite renderer cycle count
REBORN                    # Trigger generational succession
```

> [!WARNING]
> **CRITICAL: Serial Congestion & Blocking Prevention (シリアル通信の詰まり・動作遅延に関する注意点)**
> On the ESP32-S3 hardware USB-CDC (Virtual COM Port), buffer saturation in serial transmit/receive queues can cause the firmware's main loop (E-Ink rendering and biological simulation) to block, leading to extreme latency or complete system freezing. Adhere strictly to the following architectural principles:
> 
> 1. **Prevent TX Blocking When Host is Disconnected or Reading is Stalled (送信ブロッキング防止)**:
>    - If the host PC has not opened the serial port or stalls reading incoming data, the TX FIFO buffer fills up, causing internal `Serial.print()` / `Serial.println()` calls to block waiting for available buffer space.
>    - Always check `Serial.availableForWrite()` before writing, or implement defensive telemetry dropping when buffers are saturated.
> 2. **Enforce Strictly Non-Blocking Serial Ingestion (受信処理の完全非ブロッキング化)**:
>    - Never use blocking APIs such as `Serial.readStringUntil('\n')`. If a trailing newline is dropped, the entire main loop freezes until timeout expiration.
>    - Poll incoming bytes with `Serial.available()` and accumulate them one by one into a non-blocking line/ring buffer.
> 3. **Throttle Command Emission from Companion Apps (PCコンパニオン側での高頻度連投の抑制)**:
>    - Companion software (such as `companion.py`) must avoid flooding the MCU with rapid bursts of commands, which overflows the RX FIFO and causes packet corruption. Introduce appropriate command throttling and pacing intervals.

---

## PC 3D Companion Station

The companion station (`pc-companion/companion.py`) provides an interactive 3D observation terrarium powered by **Raylib**:

<p align="center">
  <img src="docs/pc_companion_station.png" width="800" alt="PC 3D Companion Station Screen"/>
</p>

### Real-Time 2.9" Virtual E-Ink Display Mirror (296x128)
<p align="center">
  <img src="docs/virtual_eink_mirror.png" width="550" alt="Virtual E-Ink Display Mirror"/>
</p>

```bash
cd pc-companion
run.bat   # Windows one-click launcher (or: uv run companion.py)
```

* **3D Voxel Terrarium**: Real-time rendering of your creature with dynamic lighting, animations, and rotating Brian's Brain CA hologram.
* **Virtual E-Ink Mirror**: Pixel-perfect 296x128 monochrome display emulation updated in real-time with physical device state.
* **8-Bit Retro Audio Engine**: 36 procedural chiptune sound effects covering all physical and social interactions (feed, play, sleep, wake, bond, combat, evolution, tournament fanfare).
* **8-Player Tournament Arena**: Single-elimination competitive bracket with automatic AI progression, live damage calculations, and crown awards.
* **Morph Encyclopedia (M-Key)**: In-app dex detailing all 12 species, innate aptitude tiers, and care evolution branching rules.
* **Social Radar**: Visualizes nearby discovered LoRa creatures, distances, and affinity statuses (`NEUTRAL`, `BONDED`, `RIVAL`).
* **Telemetry & Care Deck**: Interactive control terminal (`FEED`, `PLAY`, `TRAIN`, `PET`, `TIME SYNC`, `SNAPSHOT`).

---

## Building & Flashing

Firmware is specifically tailored for the **Heltec Vision Master E290** (ESP32-S3R8 + 2.9" E-Ink + SX1262 LoRa).

### Prerequisites
* [arduino-cli](https://arduino.github.io/arduino-cli/) with the `esp32` core installed:
  ```bash
  arduino-cli core install esp32:esp32
  ```

### Build & Flash Firmware (Target: Heltec Vision Master E290)
```bash
# Compile firmware
arduino-cli compile -b "esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB" InkLife.ino

# Flash to device (replace COM24 with your serial port)
arduino-cli upload -b "esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB" -p COM24 InkLife.ino
```

---

## Repository Structure

```text
InkLife/
├── InkLife.ino             # Core entry point (setup, loop, FreeRTOS tasks)
├── src/
│   ├── display/            # Screen rendering (GxEPD2, 60 XBM morph arts, chimera anchors)
│   ├── life/               # 48-byte packed Creature model & state transitions
│   ├── behavior/           # Utility AI (action selection & hysteresis)
│   ├── ui/                 # Action servos (feed, play, MF2 training & overwork)
│   ├── genetics/           # Breeding, mutation & 4-zone chimera fusion
│   ├── env/                # 48x12 Brian's Brain CA & RF entropy pool
│   ├── radio/              # SX1262 LoRa ad-hoc mesh protocol
│   ├── hardware/           # GPIO, power rails, debounced buttons
│   ├── core/               # FreeRTOS background worker tasks (Core 0)
│   ├── power/              # Deep sleep & battery voltage monitoring
│   ├── storage/            # High-endurance Flash NVS persistence
│   └── time/               # RTC timekeeping & epoch calculation
├── assets/                 # 96x96 1-bit master pixel art assets
├── pc-companion/           # 3D Raylib desktop observation station
└── tools/                  # Art conversion pipelines (jpg2ink.py, make_artjs.cjs)
```

---

## License

This project is licensed under the [MIT License](LICENSE).
