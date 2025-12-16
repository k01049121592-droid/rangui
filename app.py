import streamlit as st
import pandas as pd
import altair as alt
import re
from pathlib import Path

# ============================================================================
# 페이즈 1: 데이터 로드 및 전처리
# ============================================================================

@st.cache_data
def load_raw_data(file_path: str) -> pd.DataFrame:
    """
    CSV 파일을 로드합니다.
    
    Args:
        file_path: CSV 파일 경로
        
    Returns:
        원본 DataFrame
    """
    try:
        # UTF-8로 먼저 시도
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        # CP949로 재시도
        df = pd.read_csv(file_path, encoding='cp949')
    
    return df


def clean_time_slot(time_str: str) -> str:
    """
    시간대 문자열을 정규화합니다.
    
    예: "5시30분" → "05:30", "12시00분" → "12:00"
    
    Args:
        time_str: 원본 시간 문자열
        
    Returns:
        정규화된 시간 문자열 (HH:MM)
    """
    # "5시30분" 형태에서 숫자 추출
    match = re.match(r'(\d+)시(\d+)분', time_str)
    if match:
        hour = match.group(1).zfill(2)  # 2자리로 패딩
        minute = match.group(2).zfill(2)
        return f"{hour}:{minute}"
    return time_str


def clean_congestion(value) -> float:
    """
    혼잡도 값을 정리합니다.
    
    - 공백 제거
    - float 타입 변환
    - 비정상 값은 NaN 처리
    
    Args:
        value: 원본 혼잡도 값
        
    Returns:
        정리된 float 값
    """
    if pd.isna(value):
        return float('nan')
    
    # 문자열인 경우 공백 제거
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return float('nan')
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return float('nan')


def transform_wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    와이드 형태의 데이터를 롱 포맷으로 변환합니다.
    
    Args:
        df: 원본 DataFrame (와이드 형태)
        
    Returns:
        롱 포맷 DataFrame
    """
    # 기준 컬럼 (ID 변수)
    id_cols = ['요일구분', '호선', '역번호', '출발역', '상하구분']
    
    # 시간 컬럼 (값 변수) - 나머지 모든 컬럼
    time_cols = [col for col in df.columns if col not in id_cols]
    
    # melt로 롱 포맷 변환
    df_long = pd.melt(
        df,
        id_vars=id_cols,
        value_vars=time_cols,
        var_name='time_slot',
        value_name='congestion'
    )
    
    # 컬럼명 표준화
    df_long = df_long.rename(columns={
        '요일구분': 'day_type',
        '호선': 'line',
        '역번호': 'station_id',
        '출발역': 'station_name',
        '상하구분': 'direction'
    })
    
    # 시간대 정규화
    df_long['time_slot'] = df_long['time_slot'].apply(clean_time_slot)
    
    # 혼잡도 정리
    df_long['congestion'] = df_long['congestion'].apply(clean_congestion)
    
    # station_id를 int로 변환
    df_long['station_id'] = pd.to_numeric(df_long['station_id'], errors='coerce').astype('Int64')
    
    return df_long


def get_data_quality_report(df: pd.DataFrame) -> dict:
    """
    데이터 품질 검사 리포트를 생성합니다.
    
    Args:
        df: 롱 포맷 DataFrame
        
    Returns:
        품질 지표 딕셔너리
    """
    report = {}
    
    # 기본 통계
    report['total_records'] = len(df)
    report['total_missing'] = df['congestion'].isna().sum()
    report['missing_pct'] = (report['total_missing'] / report['total_records'] * 100)
    
    # 0.0 값 통계
    zero_count = (df['congestion'] == 0.0).sum()
    report['zero_count'] = zero_count
    report['zero_pct'] = (zero_count / report['total_records'] * 100)
    
    # 혼잡도 통계 (NaN 제외)
    valid_congestion = df['congestion'].dropna()
    if len(valid_congestion) > 0:
        report['min_congestion'] = valid_congestion.min()
        report['max_congestion'] = valid_congestion.max()
        report['mean_congestion'] = valid_congestion.mean()
        report['median_congestion'] = valid_congestion.median()
        
        # 이상치 확인 (음수)
        negative_count = (valid_congestion < 0).sum()
        report['negative_count'] = negative_count
        
        # 100 초과 값
        over_100_count = (valid_congestion > 100).sum()
        report['over_100_count'] = over_100_count
    else:
        report['min_congestion'] = None
        report['max_congestion'] = None
        report['mean_congestion'] = None
        report['median_congestion'] = None
        report['negative_count'] = 0
        report['over_100_count'] = 0
    
    # 유니크 값 통계
    report['unique_stations'] = df['station_name'].nunique()
    report['unique_lines'] = df['line'].nunique()
    report['unique_day_types'] = df['day_type'].nunique()
    
    return report


@st.cache_data
def load_and_process_data(file_path: str) -> pd.DataFrame:
    """
    데이터 로드와 전처리를 통합한 함수입니다.
    
    Args:
        file_path: CSV 파일 경로
        
    Returns:
        전처리된 롱 포맷 DataFrame
    """
    # 1. 원본 로드
    df_raw = load_raw_data(file_path)
    
    # 2. 와이드 → 롱 변환 및 정리
    df_processed = transform_wide_to_long(df_raw)
    
    return df_processed


# ============================================================================
# 페이즈 2: 필터 및 집계 함수
# ============================================================================

def filter_data(df: pd.DataFrame, day_type: str, line: str, station: str, 
                direction: str, start_time: str, end_time: str) -> pd.DataFrame:
    """
    필터 조건에 따라 데이터를 필터링합니다.
    
    Args:
        df: 전처리된 DataFrame
        day_type: 요일구분
        line: 호선
        station: 역명
        direction: 방향
        start_time: 시작 시간
        end_time: 종료 시간
        
    Returns:
        필터링된 DataFrame
    """
    filtered = df[
        (df['day_type'] == day_type) &
        (df['line'] == line) &
        (df['station_name'] == station) &
        (df['direction'] == direction) &
        (df['time_slot'] >= start_time) &
        (df['time_slot'] <= end_time)
    ].copy()
    
    return filtered


def calculate_kpis(filtered_df: pd.DataFrame) -> dict:
    """
    KPI 지표를 계산합니다.
    
    Args:
        filtered_df: 필터링된 DataFrame
        
    Returns:
        KPI 딕셔너리 (max_congestion, peak_time, avg_congestion)
    """
    kpis = {}
    
    # NaN 제외한 데이터
    valid_data = filtered_df.dropna(subset=['congestion'])
    
    if len(valid_data) > 0:
        kpis['max_congestion'] = valid_data['congestion'].max()
        max_idx = valid_data['congestion'].idxmax()
        kpis['peak_time'] = valid_data.loc[max_idx, 'time_slot']
        kpis['avg_congestion'] = valid_data['congestion'].mean()
    else:
        kpis['max_congestion'] = 0.0
        kpis['peak_time'] = 'N/A'
        kpis['avg_congestion'] = 0.0
    
    return kpis


# ============================================================================
# 메인 UI (페이즈 2: MVP)
# ============================================================================

def main():
    st.set_page_config(page_title="서울 지하철 혼잡도 대시보드", layout="wide")
    st.title("🚇 서울 지하철 혼잡도 대시보드")
    st.markdown("**페이즈 2**: 혼잡도 분석 및 시각화")
    
    # 데이터 파일 경로
    data_file = "서울교통공사_지하철혼잡도정보_20250930.csv"
    
    # 파일 존재 여부 확인
    if not Path(data_file).exists():
        st.error(f"데이터 파일을 찾을 수 없습니다: {data_file}")
        st.info("현재 디렉토리에 CSV 파일이 있는지 확인해주세요.")
        return
    
    # 데이터 로드 및 전처리
    with st.spinner("데이터를 로드하고 전처리 중입니다..."):
        df = load_and_process_data(data_file)
    
    # ========================================================================
    # Sidebar 필터
    # ========================================================================
    with st.sidebar:
        st.header("🔍 필터")
        
        # 요일구분
        day_types = sorted(df['day_type'].unique().tolist())
        selected_day = st.selectbox("요일구분", day_types, index=0)
        
        # 호선
        lines = sorted(df['line'].unique().tolist())
        selected_line = st.selectbox("호선", lines, index=0)
        
        # 역 선택 (해당 호선만 필터링)
        stations_in_line = df[df['line'] == selected_line]['station_name'].unique().tolist()
        selected_station = st.selectbox("역", sorted(stations_in_line), index=0)
        
        # 방향
        directions = sorted(df['direction'].unique().tolist())
        selected_direction = st.selectbox("방향", directions, index=0)
        
        # 시간대 범위
        time_slots = sorted(df['time_slot'].unique().tolist())
        st.markdown("**시간대 범위**")
        start_time, end_time = st.select_slider(
            "시간대 선택",
            options=time_slots,
            value=(time_slots[0], time_slots[-1])
        )
        
        st.markdown("---")
        st.caption(f"총 {len(df):,}개 레코드")
    
    # ========================================================================
    # 필터 적용
    # ========================================================================
    filtered_df = filter_data(
        df, 
        selected_day, 
        selected_line, 
        selected_station, 
        selected_direction,
        start_time, 
        end_time
    )
    
    # 빈 결과 처리
    if len(filtered_df) == 0:
        st.warning("⚠️ 선택한 조건에 해당하는 데이터가 없습니다.")
        st.info("다른 필터 조건을 선택해주세요.")
        st.stop()
    
    # ========================================================================
    # KPI 카드 (3개)
    # ========================================================================
    kpis = calculate_kpis(filtered_df)
    
    st.markdown("### 📊 핵심 지표")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="최대 혼잡도",
            value=f"{kpis['max_congestion']:.1f}",
            help="선택한 시간대 내 최대 혼잡도"
        )
    
    with col2:
        st.metric(
            label="피크 시간대",
            value=kpis['peak_time'],
            help="최대 혼잡도가 발생한 시간"
        )
    
    with col3:
        st.metric(
            label="평균 혼잡도",
            value=f"{kpis['avg_congestion']:.1f}",
            help="선택한 시간대 내 평균 혼잡도"
        )
    
    st.markdown("---")
    
    # ========================================================================
    # 라인차트 (시간대별 혼잡도)
    # ========================================================================
    st.markdown("### 📈 시간대별 혼잡도 추이")
    
    # NaN 제외한 데이터로 차트 생성
    chart_data = filtered_df.dropna(subset=['congestion'])
    
    if len(chart_data) > 0:
        chart = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3).encode(
            x=alt.X('time_slot:N', 
                    title='시간대',
                    sort=time_slots,
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('congestion:Q', 
                    title='혼잡도',
                    scale=alt.Scale(domain=[0, max(chart_data['congestion'].max() * 1.1, 100)])),
            tooltip=[
                alt.Tooltip('time_slot:N', title='시간대'),
                alt.Tooltip('congestion:Q', title='혼잡도', format='.1f')
            ]
        ).properties(
            title=f"{selected_station} ({selected_direction}) - {selected_day}",
            height=400
        ).configure_point(
            size=80
        ).configure_line(
            color='#1f77b4'
        )
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("표시할 데이터가 없습니다.")
    
    st.markdown("---")
    
    # ========================================================================
    # TOP 구간 테이블 + CSV 다운로드
    # ========================================================================
    st.markdown("### 🔝 혼잡 TOP 10 구간")
    
    # 혼잡 TOP 10 구간
    top_n = 10
    top_df = filtered_df.dropna(subset=['congestion']).nlargest(top_n, 'congestion')[
        ['time_slot', 'station_name', 'line', 'direction', 'congestion']
    ].reset_index(drop=True)
    
    # 순위 추가
    top_df.insert(0, '순위', range(1, len(top_df) + 1))
    
    # 컬럼명 한글화
    top_df_display = top_df.rename(columns={
        '순위': '순위',
        'time_slot': '시간대',
        'station_name': '역명',
        'line': '호선',
        'direction': '방향',
        'congestion': '혼잡도'
    })
    
    st.dataframe(
        top_df_display,
        use_container_width=True,
        hide_index=True
    )
    
    # CSV 다운로드 버튼
    csv = top_df_display.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 CSV 다운로드",
        data=csv,
        file_name=f"혼잡도_TOP{top_n}_{selected_station}_{selected_day}.csv",
        mime="text/csv",
        help="상위 혼잡 구간 데이터를 CSV 파일로 다운로드합니다."
    )
    
    # ========================================================================
    # 추가 정보 (접을 수 있음)
    # ========================================================================
    with st.expander("ℹ️ 데이터 정보"):
        st.markdown(f"""
        **필터 조건:**
        - 요일구분: {selected_day}
        - 호선: {selected_line}
        - 역: {selected_station}
        - 방향: {selected_direction}
        - 시간대: {start_time} ~ {end_time}
        
        **필터링된 데이터:** {len(filtered_df)}개 레코드
        """)
        
        st.markdown("**혼잡도 해석:**")
        st.markdown("""
        - 혼잡도는 지하철 칸의 혼잡 정도를 나타내는 지표입니다.
        - 100 이상: 매우 혼잡 (승객이 많아 불편할 수 있음)
        - 60-100: 보통 혼잡
        - 30-60: 여유 있음
        - 0-30: 매우 여유로움
        """)


if __name__ == "__main__":
    main()
