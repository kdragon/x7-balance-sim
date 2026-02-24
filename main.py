import streamlit as st
import pandas as pd
import time
import plotly.express as px
import random

st.set_page_config(page_title="X7 전투 시뮬레이터", layout="centered")

# --- 데이터 사전 정의 (공유 시트 기반) ---
DEF_CONSTANT = 500  # 방어력 상수

# 티어별 기준 스탯 (시트 데이터 기반 간소화)
# Lv1(T1), Lv30(T4), Lv60(T7)
def get_stat_by_level(level):
    # 선형 보간을 통한 레벨별 추정치 계산
    atk = 60 + (level - 1) * (948 - 60) / 59
    def_val = 120 + (level - 1) * (1696 - 120) / 59
    hp = 1500 + (level - 1) * (7400 - 1500) / 59
    mp = 200 + (level - 1) * (1000 - 200) / 59
    mp_regen = 5 + (level - 1) * (25 - 5) / 59
    return {"atk": atk, "def": def_val, "hp": hp, "mp": mp, "mp_regen": mp_regen}

def run_single_battle(c_stat, m_stat, char_aps, mon_aps, c_crit, m_crit, c_eva, m_eva, c_skill, m_skill, c_ls, m_ls, c_pot, m_pot):
    """진행된 전투의 결과와 로그를 반환합니다."""
    # 방어력에 따른 데미지 감소율 계산
    c_dmg_red = m_stat['def'] / (m_stat['def'] + DEF_CONSTANT)
    m_dmg_red = c_stat['def'] / (c_stat['def'] + DEF_CONSTANT)
    
    c_base_dmg = max(1, c_stat['atk'] * (1 - c_dmg_red))
    m_base_dmg = max(1, m_stat['atk'] * (1 - m_dmg_red))

    # 스킬 최종 데미지 (방어력 적용)
    c_skill_dmg = max(1, c_skill['dmg'] * (1 - c_dmg_red))
    m_skill_dmg = max(1, m_skill['dmg'] * (1 - m_dmg_red))

    c_hp, m_hp = c_stat['hp'], m_stat['hp']
    c_mp, m_mp = c_stat['mp'], m_stat['mp']
    seconds = 0
    c_pot_used, m_pot_used = False, False

    c_interval, m_interval = 1 / char_aps, 1 / mon_aps
    
    # 다음 액션 예정 시간
    next_c_atk, next_m_atk = c_interval, m_interval
    next_c_skill, next_m_skill = 0, 0  # 전투 시작 시 즉시 시전
    
    log = []
    while c_hp > 0 and m_hp > 0 and seconds < 100:
        # 가장 빠른 다음 이벤트(평타 or 스킬) 시간 계산
        step = min(next_c_atk - seconds, next_m_atk - seconds, 
                   next_c_skill - seconds, next_m_skill - seconds)
        seconds += step
        
        # 마나 회복
        c_mp = min(c_stat['mp'], c_mp + c_stat['mp_regen'] * step)
        m_mp = min(m_stat['mp'], m_mp + m_stat['mp_regen'] * step)
        
        # 포션 사용 판정 (체력이 임계치 이하일 때 1회 사용)
        if not c_pot_used and c_hp < c_stat['hp'] * c_pot['threshold']:
            heal = c_pot['heal']
            c_hp = min(c_stat['hp'], c_hp + heal)
            c_pot_used = True
            log.append({"Time": round(seconds, 2), "Target": "Character", 
                        "Damage": -heal, "Rem_HP": round(c_hp, 1), "Type": "Potion"})

        # 캐릭터 스킬 시전
        if seconds >= next_c_skill:
            if c_mp >= c_skill['cost']:
                c_mp -= c_skill['cost']
                m_hp -= c_skill_dmg
                log.append({"Time": round(seconds, 2), "Target": "Monster", 
                            "Damage": round(c_skill_dmg, 1), "Rem_HP": max(0, m_hp), "Type": "Skill", "MP": round(c_mp, 1)})
                next_c_skill += c_skill['cd']
            else:
                next_c_skill = seconds + 0.1 # 마나 부족 시 0.1초 후 재시도

        if m_hp <= 0: break

        if seconds >= next_c_atk:
            # 회피 판정 (공격 대상인 몬스터의 회피율 사용)
            if random.random() < m_eva:
                dmg = 0
                atk_type = "Miss"
            else:
                # 치명타 판정
                is_crit = random.random() < c_crit['rate']
                dmg = c_base_dmg * (c_crit['dmg_mult'] if is_crit else 1.0)
                atk_type = "Crit" if is_crit else "Normal"
            
            m_hp -= dmg
            # 생명력 흡수 적용
            if dmg > 0 and c_ls > 0:
                ls_heal = dmg * c_ls
                c_hp = min(c_stat['hp'], c_hp + ls_heal)

            log.append({"Time": round(seconds, 2), "Target": "Monster", "Damage": dmg, "Rem_HP": max(0, m_hp), "Type": atk_type})
            next_c_atk += c_interval
        
        # 몬스터 포션 사용 판정
        if not m_pot_used and m_hp < m_stat['hp'] * m_pot['threshold']:
            heal = m_pot['heal']
            m_hp = min(m_stat['hp'], m_hp + heal)
            m_pot_used = True
            log.append({"Time": round(seconds, 2), "Target": "Monster", 
                        "Damage": -heal, "Rem_HP": round(m_hp, 1), "Type": "Potion"})

        # 몬스터 스킬 시전
        if m_hp > 0 and seconds >= next_m_skill:
            if m_mp >= m_skill['cost']:
                m_mp -= m_skill['cost']
                c_hp -= m_skill_dmg
                log.append({"Time": round(seconds, 2), "Target": "Character", 
                            "Damage": round(m_skill_dmg, 1), "Rem_HP": max(0, c_hp), "Type": "Skill", "MP": round(m_mp, 1)})
                next_m_skill += m_skill['cd']
            else:
                next_m_skill = seconds + 0.1

        if c_hp <= 0: break

        if m_hp > 0 and seconds >= next_m_atk:
            # 회피 판정 (공격 대상인 캐릭터의 회피율 사용)
            if random.random() < c_eva:
                dmg = 0
                atk_type = "Miss"
            else:
                is_crit = random.random() < m_crit['rate']
                dmg = m_base_dmg * (m_crit['dmg_mult'] if is_crit else 1.0)
                atk_type = "Crit" if is_crit else "Normal"
            
            c_hp -= dmg
            # 생명력 흡수 적용
            if dmg > 0 and m_ls > 0:
                ls_heal = dmg * m_ls
                m_hp = min(m_stat['hp'], m_hp + ls_heal)

            log.append({"Time": round(seconds, 2), "Target": "Character", "Damage": dmg, "Rem_HP": max(0, c_hp), "Type": atk_type})
            next_m_atk += m_interval
            
    return {
        "winner": "Character" if m_hp <= 0 else "Monster",
        "log": log,
        "seconds": seconds,
        "m_hp": m_hp,
        "c_hp": c_hp
    }

st.title("⚔️ X7 실시간 전투 시뮬레이터")

# --- 사이드바: 설정 ---
st.sidebar.header("🕹️ 전투 유닛 설정")
c_lv = st.sidebar.number_input("캐릭터 레벨", 1, 60, 1)
m_lv = st.sidebar.number_input("몬스터 레벨", 1, 60, 1)

# 공격 속도 설정 (초당 공격 횟수)
char_aps = st.sidebar.slider("캐릭터 공속 (초당 횟수)", 0.5, 3.0, 1.2)
mon_aps = st.sidebar.slider("몬스터 공속 (초당 횟수)", 0.5, 3.0, 1.0)

st.sidebar.divider()
st.sidebar.subheader("🎯 치명타 설정")
c_crit_rate = st.sidebar.slider("캐릭터 치명타 확률 (%)", 0, 100, 20) / 100
c_crit_mult = st.sidebar.slider("캐릭터 치명타 피해 (%)", 100, 300, 150) / 100

m_crit_rate = st.sidebar.slider("몬스터 치명타 확률 (%)", 0, 100, 5) / 100
m_crit_mult = st.sidebar.slider("몬스터 치명타 피해 (%)", 100, 300, 150) / 100

st.sidebar.subheader("🛡️ 회피 설정")
c_eva_rate = st.sidebar.slider("캐릭터 회피율 (%)", 0, 100, 10) / 100
m_eva_rate = st.sidebar.slider("몬스터 회피율 (%)", 0, 100, 5) / 100

st.sidebar.subheader("🪄 스킬 설정")
c_skill_dmg_val = st.sidebar.number_input("캐릭터 스킬 데미지", 0, 5000, 500)
c_skill_cost_val = st.sidebar.number_input("캐릭터 스킬 마나 소모", 0, 500, 50)
c_skill_cd_val = st.sidebar.slider("캐릭터 스킬 쿨타임 (초)", 1.0, 20.0, 8.0)

m_skill_dmg_val = st.sidebar.number_input("몬스터 스킬 데미지", 0, 5000, 300)
m_skill_cost_val = st.sidebar.number_input("몬스터 스킬 마나 소모", 0, 500, 30)
m_skill_cd_val = st.sidebar.slider("몬스터 스킬 쿨타임 (초)", 1.0, 20.0, 10.0)

st.sidebar.subheader("🩸 유지력 설정")
c_ls_rate = st.sidebar.slider("캐릭터 생명력 흡수 (%)", 0, 100, 10) / 100
c_pot_heal = st.sidebar.number_input("캐릭터 포션 회복량", 0, 2000, 500)

m_ls_rate = st.sidebar.slider("몬스터 생명력 흡수 (%)", 0, 100, 0) / 100
m_pot_heal = st.sidebar.number_input("몬스터 포션 회복량", 0, 2000, 0)


num_rounds = st.sidebar.number_input("시뮬레이션 횟수", 1, 1000, 100)

# --- 시뮬레이션 로직 ---
if st.button("전투 시작!", type="primary"):
    c_stat = get_stat_by_level(c_lv)
    m_stat = get_stat_by_level(m_lv)
    
    results = []
    with st.spinner(f'{num_rounds}회 시뮬레이션 중...'):
        for _ in range(num_rounds):
            results.append(run_single_battle(
                c_stat, m_stat, char_aps, mon_aps, 
                {"rate": c_crit_rate, "dmg_mult": c_crit_mult},
                {"rate": m_crit_rate, "dmg_mult": m_crit_mult},
                c_eva_rate, m_eva_rate,
                {"dmg": c_skill_dmg_val, "cd": c_skill_cd_val, "cost": c_skill_cost_val},
                {"dmg": m_skill_dmg_val, "cd": m_skill_cd_val, "cost": m_skill_cost_val},
                c_ls_rate, m_ls_rate,
                {"heal": c_pot_heal, "threshold": 0.3},
                {"heal": m_pot_heal, "threshold": 0.3}))

    # 통계 계산
    wins = sum(1 for r in results if r['winner'] == "Character")
    win_rate = (wins / num_rounds) * 100
    avg_time = sum(r['seconds'] for r in results) / num_rounds
    
    st.subheader("📊 시뮬레이션 결과 요약")
    col1, col2, col3 = st.columns(3)
    col1.metric("승률", f"{win_rate:.1f}%")
    col2.metric("평균 전투 시간", f"{avg_time:.1f}초")
    col3.metric("총 시도 횟수", f"{num_rounds}회")

    # 상세 스펙 요약 (첫 번째 라운드 기준)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**캐릭터 (Lv.{c_lv})**\n\nHP: {c_stat['hp']:.0f} / MP: {c_stat['mp']:.0f}\n\nATK: {c_stat['atk']:.1f} / Regen: {c_stat['mp_regen']:.1f}")
    with col2:
        st.warning(f"**몬스터 (Lv.{m_lv})**\n\nHP: {m_stat['hp']:.0f} / MP: {m_stat['mp']:.0f}\n\nATK: {m_stat['atk']:.1f} / Regen: {m_stat['mp_regen']:.1f}")

    # 마지막 라운드 로그 시각화
    st.write("### 📈 샘플 전투 로그 (마지막 라운드)")
    log_df = pd.DataFrame(results[-1]['log'])
    if not log_df.empty:
        fig = px.line(log_df, x="Time", y="Rem_HP", color="Target", markers=True, hover_data=["Damage", "Type", "MP"])
        st.plotly_chart(fig)