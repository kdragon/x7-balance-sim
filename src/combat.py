import random
from typing import List
from src.config import DEF_CONSTANT, Character, Monster

def run_encounter(character: Character, monsters: List[Monster]):
    """
    하나의 전투(인카운터) 시뮬레이션을 실행합니다.
    - 캐릭터 1명 vs 몬스터 1~N명
    - Q/W/E/R 스킬 및 쿨다운 관리
    - 플레이어 숙련도 기반 회피
    """
    
    # 1. 초기 설정
    log = []
    seconds = 0.0

    # 숙련도별 회피 확률
    proficiency_dodge_map = {"하": 0.05, "중": 0.15, "상": 0.30}
    char_dodge_rate = proficiency_dodge_map.get(character.proficiency, 0.15)

    # 전투 참여자 데이터 초기화
    char_hp = character.stats['hp']
    char_mp = character.stats['mp']
    monster_hps = {i: m.stats['hp'] for i, m in enumerate(monsters)}
    
    # 다음 행동 시간 (기본 공격, 스킬)
    char_attack_interval = 1 / character.stats['aps']
    monster_attack_intervals = {i: 1 / m.stats['aps'] for i, m in enumerate(monsters)}

    next_char_attack_time = char_attack_interval
    next_monster_attack_times = {i: monster_attack_intervals[i] for i in range(len(monsters))}
    
    char_skill_cooldowns = {skill.name: 0.0 for skill in character.skills}
    monster_skill_cooldowns = {i: {skill.name: 0.0 for skill in m.skills} for i, m in enumerate(monsters)}

    log.append({"time": seconds, "message": "전투 시작!"})
    
    # 2. 전투 루프
    while char_hp > 0 and any(hp > 0 for hp in monster_hps.values()):
        # --- 다음 행동 결정 ---
        # 사용 가능한 스킬 찾기 (즉시 시전 가능)
        skill_to_use = None
        for skill in character.skills:
            if char_mp >= skill.mana_cost and seconds >= char_skill_cooldowns[skill.name]:
                skill_to_use = skill
                break # 첫번째 사용가능한 스킬 사용
        
        # 다음 캐릭터 행동 시간
        # 스킬이 있으면 즉시, 없으면 다음 기본 공격 시간
        char_action_wait = 0.0 if skill_to_use else (next_char_attack_time - seconds)
        
        # 몬스터들의 다음 행동 시간
        monster_attack_waits = {i: t - seconds for i, t in next_monster_attack_times.items() if monster_hps[i] > 0}
        if not monster_attack_waits: # 살아있는 몬스터가 없으면 루프 종료
             break

        # 다음 이벤트까지의 최소 시간
        time_step = max(0, min(char_action_wait, *monster_attack_waits.values()))
        seconds += time_step
        
        # --- 캐릭터 행동 실행 ---
        # 캐릭터의 행동 시간이 가장 가까운 이벤트일 경우
        if char_action_wait - time_step <= 0.001:
            alive_monsters = {i: hp for i, hp in monster_hps.items() if hp > 0}
            if not alive_monsters: break
            target_id = min(alive_monsters, key=alive_monsters.get)

            if skill_to_use: # 스킬 사용
                damage = skill_to_use.damage * (1 - monsters[target_id].stats['def'] / (monsters[target_id].stats['def'] + DEF_CONSTANT))
                monster_hps[target_id] -= damage
                char_mp -= skill_to_use.mana_cost
                char_skill_cooldowns[skill_to_use.name] = seconds + skill_to_use.cooldown
                log.append({"time": round(seconds, 1), "attacker": "Character", "target": f"Monster_{target_id}", "damage": round(damage, 1), "action": f"Skill: {skill_to_use.name}"})
            else: # 기본 공격
                damage = character.stats['atk'] * (1 - monsters[target_id].stats['def'] / (monsters[target_id].stats['def'] + DEF_CONSTANT))
                monster_hps[target_id] -= damage
                log.append({"time": round(seconds, 1), "attacker": "Character", "target": f"Monster_{target_id}", "damage": round(damage, 1), "action": "Attack"})
                next_char_attack_time = seconds + char_attack_interval # 기본 공격 시간만 갱신
        
        # --- 몬스터 행동 실행 ---
        for i, m in enumerate(monsters):
            if monster_hps[i] > 0 and (next_monster_attack_times[i] - seconds) <= 0.001:
                if random.random() < char_dodge_rate:
                    log.append({"time": round(seconds, 1), "attacker": f"Monster_{i}", "target": "Character", "damage": 0, "action": "Dodge"})
                else:
                    damage = m.stats['atk'] * (1 - character.stats['def'] / (character.stats['def'] + DEF_CONSTANT))
                    char_hp -= damage
                    log.append({"time": round(seconds, 1), "attacker": f"Monster_{i}", "target": "Character", "damage": round(damage, 1)})
                next_monster_attack_times[i] = seconds + monster_attack_intervals[i]

        if seconds > 120: # 전투 시간 제한
            log.append({"time": round(seconds, 1), "message": "전투 시간 초과"})
            break

    
    # 3. 전투 종료 및 결과 반환
    winner = "Character" if char_hp > 0 else "Monsters"
    log.append({"time": round(seconds, 1), "message": f"전투 종료. 승자: {winner}"})
    
    gained_exp = 0
    gained_gold = 0
    looted_items = [] # TODO: Loot table 구현

    if winner == "Character":
        for i, m in enumerate(monsters):
            # 몬스터마다 설정된 경험치와 골드를 획득
            # Monster 데이터 클래스에 exp 속성 추가 필요 (현재는 가정)
            gained_exp += m.stats.get('exp', 20) 
            gained_gold += m.gold_drop

    return {
        "winner": winner, 
        "seconds": seconds, 
        "gained_exp": gained_exp,
        "gained_gold": gained_gold,
        "looted_items": looted_items,
        "log": log,
        "char_hp_remaining": char_hp 
    }
