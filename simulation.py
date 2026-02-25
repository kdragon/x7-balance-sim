import time
import os
import csv
import random
import argparse

# =========================================================
#  데이터 디렉터리
# =========================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# =========================================================
#  CSV 로드
# =========================================================
def _load_level_exp_table(version: str = "v1") -> dict:
    """레벨업 요구 경험치 테이블 로드. 지정 버전 열을 읽음. 값이 비어 있는 행은 건너뜀."""
    table = {}
    with open(os.path.join(DATA_DIR, "level_exp.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            exp_str = row.get(version, "").strip()
            if exp_str:
                table[int(row["레벨"])] = int(exp_str)
    return table


def _available_exp_versions() -> list:
    """level_exp.csv 에서 사용 가능한 EXP 버전 열 이름 목록 반환 (레벨 열 제외)."""
    with open(os.path.join(DATA_DIR, "level_exp.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [col for col in reader.fieldnames if col != "레벨"]


def _load_monster_templates(exp_version: str = "v1") -> dict:
    """몬스터 티어별 기본 스탯 로드. exp_version 에 해당하는 기본경험치 열을 읽음.
    해당 버전의 경험치 데이터가 없으면 빈 dict 반환."""
    exp_col = f"기본경험치_{exp_version}"
    templates = {}
    with open(os.path.join(DATA_DIR, "monster_tier.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tier_num = int(row["티어"].replace("Tier", ""))
            exp_str  = row.get(exp_col, "").strip()
            if not exp_str:
                return {}   # 해당 버전의 경험치 데이터 없음
            hunt_str = row["사냥시간"].strip()
            templates[tier_num] = {
                "name":         row["이름"],
                "tier":         tier_num,
                "atk":          float(row["기본공격력"]),
                "defe":         float(row["기본방어력"]),
                "hp":           float(row["기본HP"]),
                "attack_speed": float(row["기본공격속도"]),
                "exp":          int(exp_str),
                "hunt_time":    float(hunt_str) if hunt_str else None,
            }
    return templates


def _load_difficulty_table() -> dict:
    """몬스터 난이도 배율 테이블 로드."""
    table = {}
    with open(os.path.join(DATA_DIR, "monster_difficulty.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            table[row["난이도"]] = {
                "atk_def_mult": float(row["공방배율"]),
                "hp_mult":      float(row["체력배율"]),
                "exp_mult":     float(row["경험치배율"]),
            }
    return table


def _load_character_tier_table() -> dict:
    """캐릭터 티어별 기준 공격력/방어력 로드."""
    table = {}
    with open(os.path.join(DATA_DIR, "character_tier.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tier_num = int(row["티어"].replace("Tier", ""))
            table[tier_num] = {
                "atk":  int(row["공격력"]),
                "defe": int(row["방어력"]),
            }
    return table


def _load_potion_table() -> list:
    """포션 목록 로드 (등급 순서 유지: 하급→중급→상급→최상급)."""
    result = []
    with open(os.path.join(DATA_DIR, "potion.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result.append({"name": row["이름"], "heal": int(row["회복수치"])})
    return result


def _load_food_table() -> list:
    """음식 목록 로드 (등급 순서 유지: 하급→중급→상급→최상급)."""
    result = []
    with open(os.path.join(DATA_DIR, "food.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result.append({"name": row["이름"], "heal": int(row["회복수치"])})
    return result


# 모듈 임포트 시 CSV 읽기
LEVEL_EXP_TABLE      = _load_level_exp_table("v1")  # 기본값 (Character 생성 시 fallback)
MONSTER_TEMPLATES    = _load_monster_templates("v1")  # 기본값 (Monster 생성 시 fallback)
DIFFICULTY_TABLE     = _load_difficulty_table()
CHARACTER_TIER_TABLE = _load_character_tier_table()
POTION_TABLE         = _load_potion_table()
FOOD_TABLE           = _load_food_table()

# ── 소비 아이템 설정 ──────────────────────────────────────
POTION_COOLDOWN     = 60.0   # 포션 쿨타임 (초) — 전투 중 사용
FOOD_COOLDOWN       = 20.0   # 음식 쿨타임 (초) — 전투 외 사용
POTION_HP_THRESHOLD = 0.5    # HP 50% 미만일 때 포션 자동 사용


# =========================================================
#  데미지 계산 공식
# =========================================================
def calc_damage(raw_atk: float, target_def: float) -> float:
    """
    방어력 감소 공식: actual = raw * (1 - def / (def + 500))
    최소 1 데미지 보장
    """
    reduction = target_def / (target_def + 500.0)
    return max(1.0, raw_atk * (1.0 - reduction))


# =========================================================
#  스킬
# =========================================================
class Skill:
    """스킬 정보"""
    def __init__(self, name, description, multiplier, cast_time, cooldown, mana_cost, is_aoe=False):
        self.name = name
        self.description = description
        self.multiplier = multiplier
        self.cast_time = cast_time
        self.cooldown = cooldown
        self.mana_cost = mana_cost
        self.is_aoe = is_aoe
        self.last_used_time = -cooldown   # 시뮬레이션 시작 시 즉시 사용 가능

    def is_ready(self, current_time: float) -> bool:
        return current_time - self.last_used_time >= self.cooldown


# =========================================================
#  플레이어 캐릭터
# =========================================================
class Character:
    """플레이어 캐릭터"""
    def __init__(self, level: int = 1, exp_table: dict = None):
        self.exp_table = exp_table if exp_table is not None else LEVEL_EXP_TABLE
        self.level = level
        self.max_hp = 1400 + level * 100
        self.hp = float(self.max_hp)
        self.max_mp = 340 + level * 20
        self.mp = float(self.max_mp)
        self.attack_speed = 0.9
        self.critical_rate = 0.0
        self.critical_damage = 1.2
        self.exp = 0           # 현재 레벨 내 누적 EXP (레벨업 시 초과분만 이월)
        self.total_exp = 0     # 전체 누적 EXP (통계용)
        _ct = min((level - 1) // 10 + 1, max(CHARACTER_TIER_TABLE.keys()))
        self.atk  = CHARACTER_TIER_TABLE[_ct]["atk"]
        self.defe = CHARACTER_TIER_TABLE[_ct]["defe"]
        self.skills = {
            "Q": Skill("Q", "강력한 일격", 2.0, 1.0,  5.0, 10),
            "W": Skill("W", "연속 베기",   2.5, 1.0, 12.0, 30, is_aoe=True),
            "E": Skill("E", "방어 강화",   1.5, 1.0, 15.0, 15),
            "R": Skill("R", "궁극기",      4.0, 1.0, 40.0, 50, is_aoe=True),
        }
        self.last_basic_attack_time = -999.0
        self.last_potion_time = -POTION_COOLDOWN  # 시작 시 즉시 사용 가능
        self.last_food_time   = -FOOD_COOLDOWN    # 시작 시 즉시 사용 가능

    def add_exp(self, amount: int) -> list:
        """
        EXP 추가 및 레벨업 자동 처리.
        LEVEL_EXP_TABLE 은 '해당 레벨에서 다음 레벨까지 요구되는 EXP'.
        레벨업 시 초과 EXP 이월, 달성한 새 레벨 번호 목록 반환.
        """
        self.total_exp += amount
        self.exp += amount
        new_levels = []
        while self.level in self.exp_table and self.exp >= self.exp_table[self.level]:
            self.exp -= self.exp_table[self.level]   # 초과분 이월
            self.level_up()
            new_levels.append(self.level)
        return new_levels

    def level_up(self):
        """레벨업: HP/MP 증가, 티어 전환 시 ATK/DEF를 CSV 기준값으로 교체"""
        old_tier = min((self.level - 1) // 10 + 1, max(CHARACTER_TIER_TABLE.keys()))
        self.level  += 1
        self.max_hp += 100
        self.max_mp += 20
        self.hp = min(self.hp + 100, self.max_hp)
        self.mp = min(self.mp + 20,  self.max_mp)
        new_tier = min((self.level - 1) // 10 + 1, max(CHARACTER_TIER_TABLE.keys()))
        if new_tier != old_tier:
            self.atk  = CHARACTER_TIER_TABLE[new_tier]["atk"]
            self.defe = CHARACTER_TIER_TABLE[new_tier]["defe"]

    def reset_for_next_fight(self):
        """전투 사이 휴식: MP 완전 회복.
        HP 회복은 음식(전투 외)과 포션(전투 중)으로만 이루어짐.
        사망 상태(hp<=0)이면 최소 1 HP 로 유지하여 다음 전투 진행.
        스킬 쿨타임은 리셋하지 않음 — 휴식 시간 동안에도 절대 시각 기준으로 계속 경과.
        """
        if self.hp <= 0:
            self.hp = 1.0
        self.mp = float(self.max_mp)
        self.last_basic_attack_time = -999.0

    def use_skill(self, skill_name: str, current_time: float):
        """스킬 사용. (cast_time, raw_damage, label) 반환"""
        sk = self.skills[skill_name]
        if self.mp >= sk.mana_cost:
            self.mp -= sk.mana_cost
            sk.last_used_time = current_time
            raw = self.atk * sk.multiplier
            return sk.cast_time, raw, f"[스킬 {sk.name}] {sk.description}"
        return 0.0, 0.0, ""

    def basic_attack(self, current_time: float):
        """기본 공격. (attack_interval, raw_damage, label) 반환"""
        self.last_basic_attack_time = current_time
        return 1.0 / self.attack_speed, float(self.atk), "기본 공격"


# =========================================================
#  몬스터
# =========================================================
class Monster:
    """몬스터 클래스 — 티어(CSV) + 난이도(CSV) 배율로 스탯 결정"""
    def __init__(self, tier: int, index: int = 0, difficulty: str = "Normal",
                 templates: dict = None):
        data = (templates or MONSTER_TEMPLATES)[tier]
        diff = DIFFICULTY_TABLE[difficulty]
        self.index        = index
        self.name         = data["name"]
        self.tier         = data["tier"]
        self.difficulty   = difficulty
        self.atk          = data["atk"]  * diff["atk_def_mult"]
        self.defe         = data["defe"] * diff["atk_def_mult"]
        self.max_hp       = data["hp"]   * diff["hp_mult"]
        self.hp           = self.max_hp
        self.attack_speed = data["attack_speed"]
        self.exp          = round(data["exp"] * diff["exp_mult"])
        self.last_attack_time = -999.0

    def is_alive(self) -> bool:
        return self.hp > 0.0

    def take_damage(self, dmg: float):
        self.hp = max(0.0, self.hp - dmg)

    def can_attack(self, current_time: float) -> bool:
        return current_time - self.last_attack_time >= (1.0 / self.attack_speed)

    def do_attack(self, current_time: float) -> float:
        self.last_attack_time = current_time
        return self.atk

    def hp_bar(self, width: int = 20) -> str:
        ratio = self.hp / self.max_hp
        filled = int(ratio * width)
        return "[" + "#" * filled + "-" * (width - filled) + "]"


# =========================================================
#  헬퍼
# =========================================================
def _hp_bar(current: float, maximum: float, width: int = 20) -> str:
    ratio = max(0.0, current / maximum)
    filled = int(ratio * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _consumable_tier(level: int) -> int:
    """레벨에 따른 소비 아이템 등급 인덱스 반환 (0=하급, 1=중급, 2=상급, 3=최상급).
    Lv.1~10 → 0, Lv.11~25 → 1, Lv.26~40 → 2, Lv.41+ → 3
    """
    if level <= 10: return 0
    if level <= 25: return 1
    if level <= 40: return 2
    return 3


# =========================================================
#  내부 전투 코어 (출력 없음, 다중 호출용)
# =========================================================
def _fight(player: Character, monsters: list, duration: float = 300,
           sim_time: float = 0.0) -> tuple:
    """
    조용한 전투 루프 — 화면 출력 없이 전투 결과만 반환.
    player 의 HP/MP/스킬 상태를 직접 변경함.
    EXP 는 반환만 하고 적용하지 않음 (호출자가 처리).

    sim_time : 시뮬레이션 절대 시각 오프셋 (포션 쿨타임 전투 간 추적용).

    Returns
    -------
    (victory: bool, exp_gained: int, kills: int, combat_time: float)
    """
    time_step = 0.1
    current_time = 0.0
    action_end_time = 0.0

    while current_time <= duration:
        abs_time = sim_time + current_time   # 절대 시뮬레이션 시각 (스킬/포션 쿨타임 공통 기준)
        alive = [m for m in monsters if m.is_alive()]
        if not alive or player.hp <= 0.0:
            break

        # ── 플레이어 행동 ─────────────────────────────────
        if current_time >= action_end_time:
            raw_dmg = 0.0
            used_skill = None
            cast_time = 0.0

            for sk_name in ["Q", "W", "E", "R"]:
                sk = player.skills[sk_name]
                if sk.is_ready(abs_time) and player.mp >= sk.mana_cost:
                    cast_time, raw_dmg, _ = player.use_skill(sk_name, abs_time)
                    used_skill = sk
                    action_end_time = current_time + cast_time
                    break

            if raw_dmg == 0.0:
                interval = 1.0 / player.attack_speed
                if current_time - player.last_basic_attack_time >= interval:
                    cast_time, raw_dmg, _ = player.basic_attack(current_time)
                    action_end_time = current_time + cast_time

            if raw_dmg > 0.0:
                is_aoe = used_skill is not None and used_skill.is_aoe
                targets = alive if is_aoe else [alive[0]]
                for t in targets:
                    t.take_damage(calc_damage(raw_dmg, t.defe))

        # ── 몬스터 행동 ───────────────────────────────────
        for monster in alive:
            if monster.can_attack(current_time):
                player.hp = max(0.0, player.hp - calc_damage(monster.do_attack(current_time), player.defe))

        # ── 포션 자동 사용 (전투 중) ──────────────────────
        if (player.hp > 0 and
                player.hp / player.max_hp < POTION_HP_THRESHOLD and
                abs_time - player.last_potion_time >= POTION_COOLDOWN):
            potion = POTION_TABLE[_consumable_tier(player.level)]
            player.hp = min(player.max_hp, player.hp + potion["heal"])
            player.last_potion_time = abs_time

        current_time = round(current_time + time_step, 2)

    victory   = player.hp > 0.0
    kills     = sum(1 for m in monsters if not m.is_alive())
    exp_gained = sum(m.exp for m in monsters if not m.is_alive()) if victory else 0
    return victory, exp_gained, kills, current_time


# =========================================================
#  전투 시뮬레이션 (화면 출력 포함, 단일 전투)
# =========================================================
def _fight_and_log(player: Character, monsters: list, duration: float = 300, sim_time: float = 0.0):
    """
    단일 전투를 수행하며 상세 로그를 출력.
    simulate_leveling 내부에서 호출되며, player 상태를 직접 변경.
    """
    current_time = 0.0
    time_step = 0.1
    action_end_time = 0.0
    total_damage_dealt = 0.0
    total_damage_taken = 0.0
    log_messages: list = []
    LOG_DISPLAY = 18

    # 렌더링 함수
    def render():
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 78)
        print(f"   전투 로그 (플레이어 Lv.{player.level} / 몬스터 Tier {_tier_for_level(player.level)})")
        print("=" * 78)
        req_exp = player.exp_table.get(player.level, None)
        exp_str = f"{player.exp} / {req_exp}" if req_exp else f"{player.exp} (최대레벨)"
        print(f"  [플레이어 Lv.{player.level}]")
        print(f"  HP {player.hp:>6.0f} / {player.max_hp:<6}  {_hp_bar(player.hp, player.max_hp)}")
        print(f"  MP {player.mp:>6.0f} / {player.max_mp:<6}  EXP {exp_str}")
        print("-" * 78)
        for m in monsters:
            tag = " [사망]" if not m.is_alive() else ""
            print(f"  [{m.name}  Tier{m.tier}  {m.difficulty}  #{m.index + 1}]{tag}")
            print(f"  HP {m.hp:>7.0f} / {m.max_hp:<7.0f}  {m.hp_bar()}  EXP:{m.exp}")
        print("-" * 78)
        for msg in log_messages[-LOG_DISPLAY:]:
            print(msg)
        blank = LOG_DISPLAY - min(len(log_messages), LOG_DISPLAY)
        for _ in range(blank):
            print()
        print("=" * 78)
        print(f"  경과: {current_time:5.1f}s  |  "
              f"가한 피해: {total_damage_dealt:>7.0f}  |  "
              f"받은 피해: {total_damage_taken:>7.0f}")

    render()

    # 전투 루프
    while current_time <= duration:
        abs_time = sim_time + current_time   # 절대 시뮬레이션 시각 (스킬/포션 쿨타임 공통 기준)
        alive = [m for m in monsters if m.is_alive()]

        if not alive:
            log_messages.append(f"[{current_time:.1f}s] ★ 모든 몬스터 처치! 전투 승리!")
            render()
            break
        if player.hp <= 0.0:
            log_messages.append(f"[{current_time:.1f}s] ✗ 플레이어 사망. 전투 패배.")
            render()
            break

        updated = False

        # 플레이어 행동
        if current_time >= action_end_time:
            raw_dmg = 0.0
            act_label = ""
            cast_time = 0.0
            used_skill = None

            for sk_name in ["Q", "W", "E", "R"]:
                sk = player.skills[sk_name]
                if sk.is_ready(abs_time) and player.mp >= sk.mana_cost:
                    cast_time, raw_dmg, act_label = player.use_skill(sk_name, abs_time)
                    used_skill = sk
                    action_end_time = current_time + cast_time
                    break

            if raw_dmg == 0.0:
                interval = 1.0 / player.attack_speed
                if current_time - player.last_basic_attack_time >= interval:
                    cast_time, raw_dmg, act_label = player.basic_attack(current_time)
                    action_end_time = current_time + cast_time

            if raw_dmg > 0.0:
                is_aoe = used_skill is not None and used_skill.is_aoe
                targets = alive if is_aoe else [alive[0]]
                if is_aoe:
                    log_messages.append(
                        f"[{current_time:5.1f}s] {act_label:<16} → 전체 {len(targets)}마리"
                    )
                for t in targets:
                    actual = calc_damage(raw_dmg, t.defe)
                    t.take_damage(actual)
                    total_damage_dealt += actual
                    dead_mark = "  → 처치!" if not t.is_alive() else ""
                    if is_aoe:
                        log_messages.append(
                            f"           #{t.index + 1} {t.name}: "
                            f"{actual:5.0f} 피해  (HP {t.hp:>7.0f}){dead_mark}"
                        )
                    else:
                        log_messages.append(
                            f"[{current_time:5.1f}s] {act_label:<16} → {t.name}: "
                            f"{actual:5.0f} 피해  (몬 HP {t.hp:>7.0f}){dead_mark}"
                        )
                updated = True

        # 몬스터 행동
        for monster in alive:
            if monster.can_attack(current_time):
                raw_dmg = monster.do_attack(current_time)
                actual = calc_damage(raw_dmg, player.defe)
                player.hp = max(0.0, player.hp - actual)
                total_damage_taken += actual
                log_messages.append(
                    f"[{current_time:5.1f}s] {monster.name}({monster.difficulty}) 공격"
                    f"  → 플레이어: {actual:5.0f} 피해  (플 HP {player.hp:>6.0f})"
                )
                updated = True

        # 포션 자동 사용 (전투 중, HP 50% 미만)
        if (player.hp > 0 and
                player.hp / player.max_hp < POTION_HP_THRESHOLD and
                abs_time - player.last_potion_time >= POTION_COOLDOWN):
            potion = POTION_TABLE[_consumable_tier(player.level)]
            healed = min(player.max_hp, player.hp + potion["heal"]) - player.hp
            player.hp += healed
            player.last_potion_time = abs_time
            log_messages.append(
                f"[{current_time:5.1f}s] [포션] {potion['name']} 사용"
                f"  → HP +{healed:.0f}  (플 HP {player.hp:>6.0f})"
            )
            updated = True

        if updated:
            render()

        time.sleep(time_step) # 실시간 느낌을 위해 약간의 딜레이
        current_time = round(current_time + time_step, 2)

    # 전투 결과 반환
    victory = player.hp > 0.0
    kills = sum(1 for m in monsters if not m.is_alive())
    exp_gained = sum(m.exp for m in monsters if not m.is_alive()) if victory else 0
        
    return victory, exp_gained, kills, current_time


# =========================================================
#  PvP 시뮬레이션 (같은 레벨 캐릭터 1:1)
# =========================================================
def simulate_pvp(level: int, difficulty: str = "Normal"):
    """같은 레벨의 두 캐릭터 간 PvP 시뮬레이션 (1회 전투, 실시간 출력)."""
    duration  = 300.0
    time_step = 0.1

    p1 = Character(level=level)
    p2 = Character(level=level)

    current_time  = 0.0
    p1_action_end = 0.0
    p2_action_end = 0.0
    log_messages: list = []
    LOG_DISPLAY = 16

    def render():
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 78)
        print(f"   PvP 시뮬레이션  Lv.{level}  (ATK={p1.atk}  DEF={p1.defe})")
        print("=" * 78)
        for tag, p in [("P1", p1), ("P2", p2)]:
            dead = "  [사망]" if p.hp <= 0 else ""
            print(f"  [{tag}]{dead}")
            print(f"  HP {p.hp:>6.0f} / {p.max_hp:<6}  {_hp_bar(p.hp, p.max_hp)}")
            print(f"  MP {p.mp:>6.0f} / {p.max_mp:<6}")
        print("-" * 78)
        for msg in log_messages[-LOG_DISPLAY:]:
            print(msg)
        for _ in range(LOG_DISPLAY - min(len(log_messages), LOG_DISPLAY)):
            print()
        print("=" * 78)
        print(f"  경과: {current_time:5.1f}s")

    def _collect_action(player: Character, action_end: float) -> tuple:
        """이번 틱에서 플레이어의 공격을 수집. (raw_dmg, label, new_action_end) 반환."""
        if current_time < action_end:
            return 0.0, "", action_end
        for sk_name in ["Q", "W", "E", "R"]:
            sk = player.skills[sk_name]
            if sk.is_ready(current_time) and player.mp >= sk.mana_cost:
                cast_time, raw_dmg, label = player.use_skill(sk_name, current_time)
                return raw_dmg, label, current_time + cast_time
        if current_time - player.last_basic_attack_time >= 1.0 / player.attack_speed:
            cast_time, raw_dmg, label = player.basic_attack(current_time)
            return raw_dmg, label, current_time + cast_time
        return 0.0, "", action_end

    render()

    while current_time <= duration:
        if p1.hp <= 0.0 or p2.hp <= 0.0:
            break

        # 두 플레이어의 공격을 동시에 수집한 뒤 동시에 적용
        p1_raw, p1_label, p1_action_end = _collect_action(p1, p1_action_end)
        p2_raw, p2_label, p2_action_end = _collect_action(p2, p2_action_end)

        updated = False

        if p1_raw > 0.0:
            actual = calc_damage(p1_raw, p2.defe)
            p2.hp  = max(0.0, p2.hp - actual)
            log_messages.append(
                f"[{current_time:5.1f}s] P1 {p1_label:<16} → P2: {actual:5.0f}  (P2 HP {p2.hp:>6.0f})"
                + ("  → 사망!" if p2.hp <= 0 else "")
            )
            updated = True

        if p2_raw > 0.0:
            actual = calc_damage(p2_raw, p1.defe)
            p1.hp  = max(0.0, p1.hp - actual)
            log_messages.append(
                f"[{current_time:5.1f}s] P2 {p2_label:<16} → P1: {actual:5.0f}  (P1 HP {p1.hp:>6.0f})"
                + ("  → 사망!" if p1.hp <= 0 else "")
            )
            updated = True

        # ── 포션 자동 사용 (양쪽 모두, HP 50% 미만) ──────
        for tag, p in [("P1", p1), ("P2", p2)]:
            if (p.hp > 0 and
                    p.hp / p.max_hp < POTION_HP_THRESHOLD and
                    current_time - p.last_potion_time >= POTION_COOLDOWN):
                potion = POTION_TABLE[_consumable_tier(p.level)]
                healed = min(p.max_hp, p.hp + potion["heal"]) - p.hp
                p.hp += healed
                p.last_potion_time = current_time
                log_messages.append(
                    f"[{current_time:5.1f}s] [{tag} 포션] {potion['name']}"
                    f"  → HP +{healed:.0f}  ({tag} HP {p.hp:>6.0f})"
                )
                updated = True

        if updated:
            render()

        time.sleep(time_step)
        current_time = round(current_time + time_step, 2)

    # 최종 결과 메시지
    if p1.hp <= 0.0 and p2.hp <= 0.0:
        result_msg = "★ 동시 사망 - 무승부!"
    elif p1.hp <= 0.0:
        result_msg = f"★ P1 사망 - P2 승리!  (P2 남은 HP {p2.hp:.0f})"
    elif p2.hp <= 0.0:
        result_msg = f"★ P2 사망 - P1 승리!  (P1 남은 HP {p1.hp:.0f})"
    else:
        result_msg = f"★ 시간 초과 - 무승부  (P1 {p1.hp:.0f} / P2 {p2.hp:.0f})"

    log_messages.append(f"[{current_time:.1f}s] {result_msg}")
    render()

    print()
    print("=" * 60)
    print("  [PvP 결과]")
    print(f"  {result_msg}")
    print(f"  전투 시간 : {current_time:.1f} 초")
    print("=" * 60)


# =========================================================
#  레벨 → 몬스터 티어 매핑 (10레벨마다 Tier 1씩 증가)
# =========================================================
def _tier_for_level(level: int) -> int:
    """
    Lv. 1-10  → Tier 1
    Lv.11-20  → Tier 2
    Lv.21-30  → Tier 3  ...
    최대 티어는 MONSTER_TEMPLATES 에 존재하는 최고 Tier 로 제한.
    """
    tier = (level - 1) // 10 + 1
    return min(tier, max(MONSTER_TEMPLATES.keys()))


# =========================================================
#  레벨업 시뮬레이션 (Lv.1 → target_level, 출력 최소화)
# =========================================================
# =========================================================
#  레벨업 시뮬레이션 — 내부 계산 (출력 없음)
# =========================================================
def _run_leveling(target_level: int = 60, difficulty: str = "Normal",
                  exp_version: str = "v1", seed: int = None) -> dict:
    """
    레벨업 시뮬레이션 루프를 실행하고 통계 dict 를 반환 (화면 출력 없음).

    Parameters
    ----------
    exp_version : str   level_exp.csv 에서 읽을 열 이름 (예: "v1", "v2")
    seed        : int   random.seed() 값. None 이면 시드 미설정 (매 실행 다름).
    """
    if seed is not None:
        random.seed(seed)

    level_exp_table   = _load_level_exp_table(exp_version)
    if not level_exp_table:
        return {}   # 데이터가 없는 버전은 빈 dict 반환

    # 몬스터 경험치 버전 — 해당 버전 데이터 없으면 v1 fallback
    monster_templates = _load_monster_templates(exp_version) or MONSTER_TEMPLATES

    ABSORPTION_TIME = 8.0
    max_tier  = max(monster_templates.keys())

    player = Character(level=1, exp_table=level_exp_table)

    total_time      = 0.0
    total_rest_time = 0.0
    total_kills     = 0
    total_fights    = 0
    groups_2        = 0
    groups_3        = 0

    level_time = {1: 0.0}

    tier_kills       = {t: 0   for t in range(1, max_tier + 1)}
    tier_fights      = {t: 0   for t in range(1, max_tier + 1)}
    tier_groups_2    = {t: 0   for t in range(1, max_tier + 1)}
    tier_groups_3    = {t: 0   for t in range(1, max_tier + 1)}
    tier_combat_time = {t: 0.0 for t in range(1, max_tier + 1)}

    while player.level < target_level:
        tier  = _tier_for_level(player.level)
        count = 2 if random.random() < 0.4 else 3
        monsters = [Monster(tier=tier, index=i, difficulty=difficulty,
                            templates=monster_templates)
                    for i in range(count)]

        if count == 2:
            groups_2 += 1;  tier_groups_2[tier] += 1
        else:
            groups_3 += 1;  tier_groups_3[tier] += 1
        total_fights      += 1
        tier_fights[tier] += 1

        victory, exp_gained, kills, combat_time = _fight(player, monsters, sim_time=total_time)

        total_time              += combat_time
        total_kills             += kills
        tier_kills[tier]        += kills
        tier_combat_time[tier]  += combat_time

        if victory:
            for lv in player.add_exp(exp_gained):
                if lv not in level_time:
                    level_time[lv] = total_time

        player.reset_for_next_fight()

        # ── 1차 음식 섭취 (전투 직후) ──────────────────────
        if (player.hp < player.max_hp and
                total_time - player.last_food_time >= FOOD_COOLDOWN):
            food = FOOD_TABLE[_consumable_tier(player.level)]
            player.hp = min(player.max_hp, player.hp + food["heal"])
            player.last_food_time = total_time

        rest = ABSORPTION_TIME

        # ── HP 50% 이하 → 쿨타임(20초) 더 대기 후 2차 섭취 ──
        if player.hp / player.max_hp <= 0.5:
            rest += FOOD_COOLDOWN
            eat_time = total_time + rest
            if (player.hp < player.max_hp and
                    eat_time - player.last_food_time >= FOOD_COOLDOWN):
                food = FOOD_TABLE[_consumable_tier(player.level)]
                player.hp = min(player.max_hp, player.hp + food["heal"])
                player.last_food_time = eat_time

        total_rest_time += rest
        total_time      += rest

    return {
        "exp_version":      exp_version,
        "target_level":     target_level,
        "difficulty":       difficulty,
        "total_time":       total_time,
        "total_combat_time": sum(tier_combat_time.values()),
        "total_rest_time":  total_rest_time,
        "total_fights":     total_fights,
        "total_kills":      total_kills,
        "groups_2":         groups_2,
        "groups_3":         groups_3,
        "max_tier":         max_tier,
        "level_time":       level_time,
        "tier_kills":       tier_kills,
        "tier_fights":      tier_fights,
        "tier_combat_time": tier_combat_time,
    }


# =========================================================
#  레벨업 시뮬레이션 — 결과 출력
# =========================================================
def _print_leveling_stats(stats: dict):
    """_run_leveling() 반환 dict 를 받아 티어별 상세 + 전체 요약 출력."""
    target_level      = stats["target_level"]
    difficulty        = stats["difficulty"]
    exp_version       = stats["exp_version"]
    total_time        = stats["total_time"]
    total_combat_time = stats["total_combat_time"]
    total_rest_time   = stats["total_rest_time"]
    total_fights      = stats["total_fights"]
    total_kills       = stats["total_kills"]
    groups_2          = stats["groups_2"]
    groups_3          = stats["groups_3"]
    max_tier          = stats["max_tier"]
    level_time        = stats["level_time"]
    tier_kills        = stats["tier_kills"]
    tier_fights       = stats["tier_fights"]
    tier_combat_time  = stats["tier_combat_time"]

    num_tiers = (target_level - 1) // 10 + 1
    W   = 78
    DIV = "-" * W

    print("=" * W)
    print(f"  레벨업 시뮬레이션 결과  "
          f"(Lv.1 -> Lv.{target_level} / {difficulty} / EXP:{exp_version})")
    print("=" * W)

    print("  [티어별 상세 통계]")
    print(DIV)
    print(f"  {'Tier':<7} {'레벨 구간':<9} {'처치 수':>9}     {'그룹 수':>8}  "
          f"{'평균 전투(초)':>15}  {'통과 시간(분)':>16}  {'통과(시간)':>13}")
    print(DIV)

    for t in range(1, num_tiers + 1):
        if t > max_tier:
            break
        start_lv = (t - 1) * 10 + 1
        end_lv   = min(t * 10, target_level)
        t_start  = level_time.get(start_lv, 0.0)
        t_end    = level_time.get(end_lv + 1, total_time)
        duration = t_end - t_start

        avg_ct   = (tier_combat_time[t] / tier_fights[t]) if tier_fights[t] else 0.0
        if tier_fights[t] > 0:
            print(f"  {'Tier'+str(t):<7} Lv.{start_lv:>2}~{end_lv:<6} "
                  f"{tier_kills[t]:>9,}    {tier_fights[t]:>9,}  "
                  f"{avg_ct:>15.2f}  "
                  f"{duration / 60:>16.1f}  "
                  f"{duration / 3600:>13.3f}")

    print(DIV)

    avg_all = total_combat_time / total_fights if total_fights else 0.0
    print(f"\n  [Lv.1 -> Lv.{target_level} 전체 요약]")
    print(DIV)
    print(f"  총 소요 시간   : {total_time:>14,.1f} 초"
          f"  ({total_time / 60:>10,.1f} 분  /  {total_time / 3600:>8.2f} 시간)")
    print(f"  |- 전투 시간   : {total_combat_time:>14,.1f} 초"
          f"  ({total_combat_time / 60:>10,.1f} 분  /  {total_combat_time / 3600:>8.2f} 시간)")
    print(f"  +- 휴식 시간   : {total_rest_time:>14,.1f} 초"
          f"  ({total_rest_time / 60:>10,.1f} 분  /  {total_rest_time / 3600:>8.2f} 시간)")
    print(f"  총 전투 횟수   : {total_fights:>14,} 회"
          f"  (2마리 {groups_2:,}회 {groups_2/total_fights*100:.1f}%"
          f"  /  3마리 {groups_3:,}회 {groups_3/total_fights*100:.1f}%)")
    print(f"  총 처치 수     : {total_kills:>14,} 마리")
    print(f"  평균 전투 시간 : {avg_all:>14.2f} 초/전투")
    print("=" * W)


def simulate_leveling(target_level: int = 60, difficulty: str = "Normal",
                      exp_version: str = "v1", seed: int = None):
    """레벨업 시뮬레이션 실행 및 결과 출력."""
    max_tier = max(MONSTER_TEMPLATES.keys())

    level_exp_table = _load_level_exp_table(exp_version)
    if not level_exp_table:
        print(f"  [오류] EXP 버전 '{exp_version}' 에 데이터가 없습니다.")
        print(f"  level_exp.csv 의 '{exp_version}' 열을 채워주세요.")
        return

    print(f"  레벨업 시뮬레이션 시작: Lv.1 -> Lv.{target_level}"
          f"  (난이도: {difficulty} / EXP:{exp_version}"
          + (f" / seed:{seed}" if seed is not None else "") + ")")
    print(f"  티어 전환: " + "  /  ".join(
        f"Lv.{t * 10 + 1}~ Tier{t + 1}"
        for t in range(1, min((target_level - 1) // 10 + 1, max_tier))
    ))
    print("  계산 중...", end="", flush=True)

    stats = _run_leveling(target_level, difficulty, exp_version, seed)

    print(" 완료!\n")
    _print_leveling_stats(stats)


# =========================================================
#  EXP 버전 비교 시뮬레이션
# =========================================================
def simulate_comparison(target_level: int = 60, difficulty: str = "Normal",
                        seed: int = 42):
    """
    level_exp.csv 의 모든 EXP 버전을 동일 시드로 실행하여 나란히 비교 출력.
    데이터가 없는 버전(빈 열)은 건너뜀.
    """
    versions = _available_exp_versions()
    max_tier = max(MONSTER_TEMPLATES.keys())
    num_tiers = (target_level - 1) // 10 + 1

    print(f"  EXP 버전 비교 시뮬레이션: Lv.1 -> Lv.{target_level}"
          f"  (난이도: {difficulty} / seed:{seed})")
    print(f"  버전 목록: {', '.join(versions)}")
    print()

    all_stats = {}
    for ver in versions:
        tbl = _load_level_exp_table(ver)
        if not tbl:
            print(f"  [{ver}] 데이터 없음 - 건너뜀")
            continue
        print(f"  [{ver}] 계산 중...", end="", flush=True)
        all_stats[ver] = _run_leveling(target_level, difficulty, ver, seed)
        print(" 완료!")

    if not all_stats:
        print("\n  비교할 데이터가 없습니다. level_exp.csv 를 채워주세요.")
        return

    # ── 비교 표 출력 ──────────────────────────────────────
    W   = 90
    DIV = "-" * W
    ver_list = list(all_stats.keys())

    print()
    print("=" * W)
    print(f"  [EXP 버전 비교]  Lv.1 -> Lv.{target_level}  /  {difficulty}  /  seed:{seed}")
    print("=" * W)

    # 헤더
    hdr = f"  {'버전':<6} | {'총시간(h)':>10} | {'전투횟수':>8} |"
    for t in range(1, num_tiers + 1):
        if t > max_tier:
            break
        hdr += f" Tier{t}(h) |"
    print(hdr)
    print(DIV)

    for ver, st in all_stats.items():
        lv_time   = st["level_time"]
        t_total   = st["total_time"]
        t_fights  = st["total_fights"]
        t_ct      = st["tier_combat_time"]

        row = f"  {ver:<6} | {t_total/3600:>10.2f} | {t_fights:>8,} |"
        for t in range(1, num_tiers + 1):
            if t > max_tier:
                break
            start_lv = (t - 1) * 10 + 1
            end_lv   = min(t * 10, target_level)
            t_start  = lv_time.get(start_lv, 0.0)
            t_end    = lv_time.get(end_lv + 1, t_total)
            dur_h    = (t_end - t_start) / 3600
            row += f" {dur_h:>8.2f} |"
        print(row)

    print(DIV)

    # 버전 간 차이 (첫 번째 버전 대비 %)
    if len(ver_list) >= 2:
        base_ver = ver_list[0]
        base_st  = all_stats[base_ver]
        print(f"\n  [{base_ver} 대비 변화율]")
        print(DIV)
        for ver in ver_list[1:]:
            st = all_stats[ver]
            delta_pct = (st["total_time"] - base_st["total_time"]) / base_st["total_time"] * 100
            delta_h   = (st["total_time"] - base_st["total_time"]) / 3600
            sign = "+" if delta_pct >= 0 else ""
            print(f"  {ver} vs {base_ver}  |  "
                  f"총시간: {sign}{delta_pct:.1f}%  ({sign}{delta_h:.2f}h)  |  "
                  f"전투횟수: {sign}{st['total_fights']-base_st['total_fights']:,}회")
        print(DIV)

    print("=" * W)


# =========================================================
#  진입점
# =========================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MMORPG 레벨업 시뮬레이터")
    parser.add_argument("--log-tier", type=int,
                        help="단일 전투 로그를 출력할 몬스터 티어 (예: --log-tier 2).")
    parser.add_argument("--pvp", type=int, metavar="LEVEL",
                        help="PvP 시뮬레이션을 실행할 캐릭터 레벨 (예: --pvp 25).")
    parser.add_argument("--target-level", type=int, default=60,
                        help="레벨업 시뮬레이션 목표 레벨 (기본값: 60).")
    parser.add_argument("--difficulty", type=str, default="Normal",
                        choices=list(DIFFICULTY_TABLE.keys()),
                        help="난이도 (기본값: Normal).")
    parser.add_argument("--exp-ver", type=str, default="v1", metavar="VERSION",
                        help="사용할 EXP 테이블 버전 (기본값: v1). 예: --exp-ver v2")
    parser.add_argument("--compare", action="store_true",
                        help="모든 EXP 버전을 동일 시드로 실행하여 비교. "
                             "--seed 미지정 시 seed=42 사용.")
    parser.add_argument("--seed", type=int, default=None,
                        help="랜덤 시드 고정 (기본값: 없음 = 매번 다른 결과).")
    args = parser.parse_args()

    if args.pvp:
        simulate_pvp(level=args.pvp, difficulty=args.difficulty)
    elif args.log_tier:
        # ── 단일 전투 모드 ──────────────────────────────
        tier = max(1, min(args.log_tier, max(MONSTER_TEMPLATES.keys())))
        start_level = (tier - 1) * 10 + 1
        count = 2 if random.random() < 0.4 else 3
        player   = Character(level=start_level)
        monsters = [Monster(tier=tier, index=i, difficulty=args.difficulty)
                    for i in range(count)]

        print(f"  [단일 전투] Tier{tier}  Lv.{start_level}  {count}마리  (난이도: {args.difficulty})")
        print(f"  캐릭터 스탯  ATK={player.atk}  DEF={player.defe}"
              f"  HP={player.max_hp}  MP={player.max_mp}")
        print()

        victory, exp_gained, kills, combat_time = _fight_and_log(player, monsters)

        print()
        print("=" * 60)
        print("  [전투 결과]")
        print(f"  결과        : {'승리' if victory else '패배'}")
        print(f"  처치 수     : {kills} / {count} 마리")
        print(f"  획득 EXP    : {exp_gained}")
        print(f"  전투 시간   : {combat_time:.1f} 초")
        print(f"  남은 HP     : {player.hp:.0f} / {player.max_hp}")
        print("=" * 60)
    elif args.compare:
        # ── 버전 비교 모드 ───────────────────────────────
        compare_seed = args.seed if args.seed is not None else 42
        simulate_comparison(
            target_level=args.target_level,
            difficulty=args.difficulty,
            seed=compare_seed,
        )
    else:
        # ── 단일 버전 레벨업 시뮬레이션 ─────────────────
        simulate_leveling(
            target_level=args.target_level,
            difficulty=args.difficulty,
            exp_version=args.exp_ver,
            seed=args.seed,
        )
