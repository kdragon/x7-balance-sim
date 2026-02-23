import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="MMORPG 시뮬레이터", layout="wide")

st.title("🛡️ MMORPG 강화 & 성장 시뮬레이터")
st.sidebar.header("⚙️ 시뮬레이션 설정")

# 동료들이 조절할 입력값
enchant_prob = st.sidebar.slider("강화 성공 확률 (%)", 1, 100, 45) / 100
fail_penalty = st.sidebar.checkbox("실패 시 단계 하락", value=True)
num_users = st.sidebar.number_input("시뮬레이션 가상 유저 수", 100, 10000, 1000)

# 시뮬레이션 실행 함수
def run_simulation():
    all_results = []
    for _ in range(num_users):
        level = 0
        attempts = 0
        while level < 10:  # 10강이 목표
            attempts += 1
            if np.random.random() < enchant_prob:
                level += 1
            else:
                if fail_penalty and level > 0:
                    level -= 1
        all_results.append(attempts)
    return pd.DataFrame({"시도횟수": all_results})

if st.sidebar.button("시뮬레이션 시작", type="primary"):
    df = run_simulation()
    
    # 결과 요약
    col1, col2 = st.columns(2)
    with col1:
        st.metric("10강 도달 평균 시도 횟수", f"{int(df['시도횟수'].mean())}회")
        fig = px.histogram(df, x="시도횟수", title="유저별 강화 성공 분포")
        st.plotly_chart(fig)
    with col2:
        st.metric("가장 운 나쁜 유저", f"{df['시도횟수'].max()}회")
        st.write("상위 10% 유저는 평균적으로 얼마나 빨리 성공할까요?")
        st.write(df['시도횟수'].describe())
else:
    st.info("왼쪽 설정을 조절한 후 '시뮬레이션 시작' 버튼을 눌러주세요.")