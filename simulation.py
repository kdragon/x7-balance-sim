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
def _load_level_exp_table() -> dict:
    """레벨업 요구 경험치 테이블 로드. 값이 비어 있는 행은 건너뜀."""
    table = {}
    with open(os.path.join(DATA_DIR, "level_exp.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            exp_str = row["다음레벨까지요구경험치"].strip()
            if exp_str:
                table[int(row["레벨"])] = int(exp_str)
    return table


def _load_monster_templates() -> dict:
    """몬스터 티어별 기본 스탯 로드."""
    templates = {}
    with open(os.path.join(DATA_DIR, "monster_tier.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tier_num = int(row["티어"].replace("Tier", ""))
            hunt_str = row["사냥시간"].strip()
            templates[tier_num] = {
                "name":         row["이름"],
                "tier":         tier_num,
                "atk":          float(row["기본공격력"]),
                "defe":         float(row["기본방어력"]),
                "hp":           float(row["기본HP"]),
                "attack_speed": float(row["기본공격속도"]),
                "exp":          int(row["기본경험치"]),
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


# 모듈 임포트 시 CSV 읽기
LEVEL_EXP_TABLE      = _load_level_exp_table()
MONSTER_TEMPLATES    = _load_monster_templates()
DIFFICULTY_TABLE     = _load_difficulty_table()
CHARACTER_TIER_TABLE = _load_character_tier_table()


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
    def __init__(self, level: int = 1):
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

    def add_exp(self, amount: int) -> list:
        """
        EXP 추가 및 레벨업 자동 처리.
        LEVEL_EXP_TABLE 은 '해당 레벨에서 다음 레벨까지 요구되는 EXP'.
        레벨업 시 초과 EXP 이월, 달성한 새 레벨 번호 목록 반환.
        """
        self.total_exp += amount
        self.exp += amount
        new_levels = []
        while self.level in LEVEL_EXP_TABLE and self.exp >= LEVEL_EXP_TABLE[self.level]:
            self.exp -= LEVEL_EXP_TABLE[self.level]   # 초과분 이월
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
        """전투 사이 휴식: HP/MP 완전 회복, 스킬 쿨타임 초기화"""
        self.hp = float(self.max_hp)
        self.mp = float(self.max_mp)
        for sk in self.skills.values():
            sk.last_used_time = -sk.cooldown
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
    def __init__(self, tier: int, index: int = 0, difficulty: str = "Normal"):
        data = MONSTER_TEMPLATES[tier]
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


# =========================================================
#  내부 전투 코어 (출력 없음, 다중 호출용)
# =========================================================
def _fight(player: Character, monsters: list, duration: float = 300) -> tuple:
    """
    조용한 전투 루프 — 화면 출력 없이 전투 결과만 반환.
    player 의 HP/MP/스킬 상태를 직접 변경함.
    EXP 는 반환만 하고 적용하지 않음 (호출자가 처리).

    Returns
    -------
    (victory: bool, exp_gained: int, kills: int, combat_time: float)
    """
    time_step = 0.1
    current_time = 0.0
    action_end_time = 0.0

    while current_time <= duration:
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
                if sk.is_ready(current_time) and player.mp >= sk.mana_cost:
                    cast_time, raw_dmg, _ = player.use_skill(sk_name, current_time)
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

        current_time = round(current_time + time_step, 2)

    victory   = player.hp > 0.0
    kills     = sum(1 for m in monsters if not m.is_alive())
    exp_gained = sum(m.exp for m in monsters if not m.is_alive()) if victory else 0
    return victory, exp_gained, kills, current_time


# =========================================================
#  전투 시뮬레이션 (화면 출력 포함, 단일 전투)
# =========================================================
def _fight_and_log(player: Character, monsters: list, duration: float = 300):
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
        req_exp = LEVEL_EXP_TABLE.get(player.level, None)
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
                if sk.is_ready(current_time) and player.mp >= sk.mana_cost:
                    cast_time, raw_dmg, act_label = player.use_skill(sk_name, current_time)
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
def simulate_leveling(target_level: int = 60, difficulty: str = "Normal"):
    """
    레벨에 따라 몬스터 Tier 가 증가하면서 target_level 도달까지 반복 전투.
    전투별 출력 없음, 티어별 통계 및 전체 요약만 출력.
    """
    REST_TIME = 5.0
    max_tier  = max(MONSTER_TEMPLATES.keys())

    player = Character(level=1)

    # 전체 통계
    total_time   = 0.0
    total_kills  = 0
    total_fights = 0
    groups_2     = 0
    groups_3     = 0

    # 레벨별 도달 시각 (티어 구간 기간 계산용)
    level_time = {1: 0.0}

    # 티어별 세부 통계
    tier_kills       = {t: 0   for t in range(1, max_tier + 1)}
    tier_fights      = {t: 0   for t in range(1, max_tier + 1)}
    tier_groups_2    = {t: 0   for t in range(1, max_tier + 1)}
    tier_groups_3    = {t: 0   for t in range(1, max_tier + 1)}
    tier_combat_time = {t: 0.0 for t in range(1, max_tier + 1)}

    print(f"  레벨업 시뮬레이션 시작: Lv.1 -> Lv.{target_level}  (난이도: {difficulty})")
    print(f"  티어 전환: " + "  /  ".join(
        f"Lv.{t * 10 + 1}~ Tier{t + 1}"
        for t in range(1, min((target_level - 1) // 10 + 1, max_tier))
    ))
    print("  계산 중...", end="", flush=True)

    while player.level < target_level:
        tier  = _tier_for_level(player.level)
        count = 2 if random.random() < 0.4 else 3
        monsters = [Monster(tier=tier, index=i, difficulty=difficulty)
                    for i in range(count)]

        if count == 2:
            groups_2 += 1;  tier_groups_2[tier] += 1
        else:
            groups_3 += 1;  tier_groups_3[tier] += 1
        total_fights      += 1
        tier_fights[tier] += 1

        victory, exp_gained, kills, combat_time = _fight(player, monsters)

        total_time              += combat_time
        total_kills             += kills
        tier_kills[tier]        += kills
        tier_combat_time[tier]  += combat_time

        if victory:
            for lv in player.add_exp(exp_gained):
                if lv not in level_time:
                    level_time[lv] = total_time

        player.reset_for_next_fight()
        total_time += REST_TIME

    print(" 완료!\n")


    # ── 출력 ─────────────────────────────────────────────
    num_tiers  = (target_level - 1) // 10 + 1          # 사용된 티어 수
    total_combat_time = sum(tier_combat_time.values())
    total_rest_time   = total_fights * REST_TIME

    W = 78
    DIV = "-" * W

    print("=" * W)
    print(f"  레벨업 시뮬레이션 결과  (Lv.1 -> Lv.{target_level} / {difficulty})")
    print("=" * W)

    # ── 티어별 상세 ──────────────────────────────────────
    print(f"  [티어별 상세 통계]")
    print(DIV)
    print(f"  {'Tier':<7} {'레벨 구간':<9} {'처치 수':>9}     {'그룹 수':>8}  "
          f"{'평균 전투(초)':>15}  {'통과 시간(분)':>16}  {'통과(시간)':>13}")
    print(DIV)

    for t in range(1, num_tiers + 1):
        if t > max_tier:
            break
        start_lv = (t - 1) * 10 + 1
        end_lv   = min(t * 10, target_level)
        # 티어 구간 시작/끝 시각
        t_start  = level_time.get(start_lv, 0.0)
        t_end    = level_time.get(end_lv + 1, total_time)  # 다음 티어 첫 레벨 도달 시각
        duration = t_end - t_start

        avg_ct   = (tier_combat_time[t] / tier_fights[t]) if tier_fights[t] else 0.0
        kills_t  = tier_kills[t]
        fights_t = tier_fights[t]

        # 통계가 있는 경우에만 출력
        if fights_t > 0:
            print(f"  {'Tier'+str(t):<7} Lv.{start_lv:>2}~{end_lv:<6} "
                  f"{kills_t:>9,}    {fights_t:>9,}  "
                  f"{avg_ct:>15.2f}  "
                  f"{duration / 60:>16.1f}  "
                  f"{duration / 3600:>13.3f}")

    print(DIV)

    # ── 전체 요약 ─────────────────────────────────────────
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


# =========================================================
#  진입점
# =========================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MMORPG 레벨업 시뮬레이터")
    parser.add_argument("--log-tier", type=int,
                        help="단일 전투 로그를 출력할 몬스터 티어 (예: --log-tier 2). "
                             "지정 시 해당 티어 레벨의 캐릭터로 PvE 전투 1회만 실행.")
    parser.add_argument("--pvp", type=int, metavar="LEVEL",
                        help="PvP 시뮬레이션을 실행할 캐릭터 레벨 (예: --pvp 25). "
                             "지정 레벨의 두 캐릭터가 1:1 전투를 1회 실행.")
    parser.add_argument("--target-level", type=int, default=60,
                        help="레벨업 시뮬레이션 목표 레벨 (기본값: 60).")
    parser.add_argument("--difficulty", type=str, default="Normal",
                        choices=list(DIFFICULTY_TABLE.keys()),
                        help="난이도 (기본값: Normal).")
    args = parser.parse_args()

    if args.pvp:
        simulate_pvp(level=args.pvp, difficulty=args.difficulty)
    elif args.log_tier:
        # ── 단일 전투 모드 ──────────────────────────────
        tier = max(1, min(args.log_tier, max(MONSTER_TEMPLATES.keys())))
        start_level = (tier - 1) * 10 + 1          # 해당 티어의 시작 레벨
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
    else:
        # ── 레벨업 시뮬레이션 모드 ──────────────────────
        simulate_leveling(
            target_level=args.target_level,
            difficulty=args.difficulty,
        )
