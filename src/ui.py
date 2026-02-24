import streamlit as st
import pandas as pd
import plotly.express as px

from src.config import Character, Skill, Monster, HuntingGround
from src.progression import run_levelup_simulation

def main():
    st.set_page_config(page_title="X7 성장 시뮬레이터", layout="wide")
    st.title("⚔️ X7 성장 시뮬레이터")

    # --- 1. 기본 설정 (사이드바) ---
    st.sidebar.header("⚙️ 시뮬레이션 기본 설정")
    
    # 캐릭터 설정
    st.sidebar.subheader("👤 캐릭터 설정")
    char_proficiency = st.sidebar.selectbox("숙련도 (회피율)", ["하", "중", "상"], index=1)
    
    # 스킬 설정 (간소화)
    with st.sidebar.expander("🪄 스킬 설정"):
        # Q 스킬
        st.write("Q 스킬")
        q_skill_dmg = st.number_input("Q 데미지", 0, 5000, 300, key="q_dmg")
        q_skill_cd = st.slider("Q 쿨타임 (초)", 1.0, 30.0, 5.0, key="q_cd")
        q_skill_cost = st.number_input("Q 마나 소모", 0, 500, 30, key="q_cost")
        st.divider()
        # W 스킬
        st.write("W 스킬")
        w_skill_dmg = st.number_input("W 데미지", 0, 5000, 500, key="w_dmg")
        w_skill_cd = st.slider("W 쿨타임 (초)", 1.0, 60.0, 12.0, key="w_cd")
        w_skill_cost = st.number_input("W 마나 소모", 0, 500, 70, key="w_cost")

    # --- 2. 사냥터 설정 ---
    st.sidebar.header("🏞️ 사냥터 설정")
    monster_level = st.sidebar.slider("몬스터 레벨", 1, 60, 1)
    min_roaming, max_roaming = st.sidebar.slider(
        "몬스터 로밍 시간 (초)", 
        0, 60, (3, 8)
    )

    # --- 3. 시뮬레이션 실행 ---
    if st.sidebar.button("🚀 성장 시뮬레이션 시작!", type="primary"):
        
        # 가상 데이터로 모델 인스턴스화
        # 캐릭터
        player_skills = [
            Skill(name="Q", damage=q_skill_dmg, cooldown=q_skill_cd, mana_cost=q_skill_cost),
            Skill(name="W", damage=w_skill_dmg, cooldown=w_skill_cd, mana_cost=w_skill_cost),
        ]
        player = Character(level=1, skills=player_skills, proficiency=char_proficiency)

        # 몬스터 (UI에서 설정한 레벨 반영)
        monster_template = Monster(name="고블린", level=monster_level, gold_drop=int(10 * (1.1**(monster_level-1))))
        
        # 사냥터
        hunting_ground = HuntingGround(
            name="초보자 사냥터", 
            tier=1, 
            monster_types=[monster_template],
            roaming_time_range=(min_roaming, max_roaming)
        )
        
        # 시뮬레이션 실행
        st.header("📈 성장 시뮬레이션 결과")
        with st.spinner("성장 시뮬레이션을 실행 중입니다. 잠시만 기다려주세요..."):
            history_df, summary = run_levelup_simulation(player, hunting_ground)

        if history_df is not None:
            st.success(f"""
            **총 {summary['total_monsters']:,}마리**의 몬스터를 처치하여 **약 {summary['total_hours']}시간** 만에 60레벨을 달성했습니다!  
            **최종 골드: {player.gold:,}**
            """)
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("### 레벨업 상세 기록")
                st.dataframe(history_df)
            with col2:
                # 누적 시간 시각화
                st.write("### 레벨별 누적 소요 시간")
                fig = px.line(history_df, x="레벨", y="누적 시간(시간)")
                fig.update_xaxes(type='category')
                st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("사이드바에서 설정을 마친 후 '성장 시뮬레이션 시작' 버튼을 눌러주세요.")
