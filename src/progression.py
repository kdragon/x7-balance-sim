from src.config import get_stat_by_level, get_exp_for_next_level, Character, Monster, HuntingGround, CONSUMABLES
from src.combat import run_encounter

def run_levelup_simulation(character: Character, hunting_ground: HuntingGround):
    """1레벨부터 60레벨까지의 레벨업 과정을 시뮬레이션합니다."""
    
    # 시뮬레이션 상태 변수
    total_seconds = 0
    char_current_hp = character.stats['hp'] # 캐릭터의 현재 HP 추적

    # 레벨업 기록
    levelup_history = []
    
    # UI 요소
    progress_bar = st.progress(0)
    status_text = st.empty()

    for level in range(1, 60):
        character.level = level
        character.stats = get_stat_by_level(level) # Refresh stats on level up
        char_current_hp = character.stats['hp'] # 레벨업 시 HP 완전 회복
        
        exp_to_next_level = get_exp_for_next_level(level)
        exp_gained_this_level = 0
        
        monsters_killed_this_level = 0
        time_spent_this_level = 0

        while exp_gained_this_level < exp_to_next_level:
            # 1. 로밍 시간 추가
            roaming_time = random.uniform(*hunting_ground.roaming_time_range)
            time_spent_this_level += roaming_time
            
            # 2. 몬스터 그룹 생성 (여기서는 1마리만 가정)
            monsters_to_fight = [random.choice(hunting_ground.monster_types)]
            
            # 3. 전투 시뮬레이션 실행
            # 전투 시작 전 캐릭터의 현재 상태를 전투 함수에 전달해야 함 (HP 등)
            # 여기서는 character 객체를 통째로 넘기므로, combat 모듈이 알아서 사용하게 됨
            encounter_result = run_encounter(character, monsters_to_fight)
            
            # 4. 전투 결과 처리
            time_spent_this_level += encounter_result["seconds"]
            char_current_hp = encounter_result["char_hp_remaining"]

            if encounter_result["winner"] == "Character":
                exp_gained_this_level += encounter_result["gained_exp"]
                character.gold += encounter_result["gained_gold"]
                monsters_killed_this_level += len(monsters_to_fight)

                # 5. HP 회복 로직
                hp_threshold = character.stats['hp'] * 0.7
                if char_current_hp < hp_threshold:
                    food = CONSUMABLES["Bread"]
                    heal_amount = food.effect["hp_restore"]
                    consume_time = food.effect["consume_time"]
                    
                    # 필요한 만큼 음식 섭취
                    while char_current_hp < character.stats['hp']:
                        char_current_hp += heal_amount
                        time_spent_this_level += consume_time
                        if char_current_hp >= character.stats['hp']:
                            char_current_hp = character.stats['hp']
                            break
            else:
                st.error(f"Lv.{level} 캐릭터가 {hunting_ground.name}에서 패배했습니다. 시뮬레이션을 중단합니다.")
                return None, None

        total_seconds += time_spent_this_level
        
        levelup_history.append({
            "레벨": f"{level} → {level+1}",
            "필요 경험치": exp_to_next_level,
            "처치 몬스터": monsters_killed_this_level,
            "소요 시간(분)": round(time_spent_this_level / 60, 2),
            "누적 몬스터": sum(h["처치 몬스터"] for h in levelup_history) + monsters_killed_this_level,
            "누적 시간(시간)": round(total_seconds / 3600, 2)
        })

        status_text.text(f"레벨 {level+1} 달성! (누적 {round(total_seconds / 3600, 2)}시간)")
        progress_bar.progress((level) / 59)

    status_text.success("🎉 60레벨 달성! 시뮬레이션 완료.")
    progress_bar.empty()

    return pd.DataFrame(levelup_history), {
        "total_monsters": sum(h["처치 몬스터"] for h in levelup_history),
        "total_hours": round(total_seconds / 3600, 2)
    }
