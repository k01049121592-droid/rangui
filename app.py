import streamlit as st
import pandas as pd
import altair as alt
import re
from pathlib import Path

# ============================================================================
# 상수 정의
# ============================================================================

# 혼잡 등급 정의: (최소값, 최대값, 색상, 이모지)
CONGESTION_LEVELS = {
    "매우 여유": (0, 30, "#3498db", "🔵"),
    "여유": (30, 60, "#2ecc71", "🟢"),
    "보통 혼잡": (60, 100, "#f1c40f", "🟡"),
    "매우 혼잡": (100, float('inf'), "#e74c3c", "🔴")
}

# ============================================================================
# 유틸리티 함수
# ============================================================================

def get_congestion_level(congestion: float) -> str:
    """
    혼잡도 값에 해당하는 등급명을 반환합니다.
    
    Args:
        congestion: 혼잡도 값
        
    Returns:
        혼잡 등급명 (예: "매우 여유", "보통 혼잡")
    """
    if pd.isna(congestion):
        return "데이터 없음"
    
    for level_name, (min_val, max_val, _, _) in CONGESTION_LEVELS.items():
        if min_val <= congestion < max_val:
            return level_name
    
    return "알 수 없음"


def get_congestion_color(congestion: float) -> str:
    """
    혼잡도 값에 해당하는 색상 코드를 반환합니다.
    
    Args:
        congestion: 혼잡도 값
        
    Returns:
        색상 코드 (예: "#3498db")
    """
    if pd.isna(congestion):
        return "#95a5a6"  # 회색
    
    for level_name, (min_val, max_val, color, _) in CONGESTION_LEVELS.items():
        if min_val <= congestion < max_val:
            return color
    
    return "#95a5a6"  # 기본 회색


def get_congestion_emoji(congestion: float) -> str:
    """
    혼잡도 값에 해당하는 이모지를 반환합니다.
    
    Args:
        congestion: 혼잡도 값
        
    Returns:
        이모지 (예: "🔵", "🟢")
    """
    if pd.isna(congestion):
        return "⚪"
    
    for level_name, (min_val, max_val, _, emoji) in CONGESTION_LEVELS.items():
        if min_val <= congestion < max_val:
            return emoji
    
    return "⚪"


# ============================================================================
# UI 헬퍼 함수
# ============================================================================

def render_kpi_with_color(label: str, value: str, congestion: float, help_text: str = None):
    """
    혼잡 등급별 색상이 적용된 KPI 카드를 렌더링합니다.
    
    Args:
        label: KPI 라벨
        value: 표시할 값
        congestion: 혼잡도 (색상 결정용)
        help_text: 도움말 텍스트
    """
    color = get_congestion_color(congestion)
    emoji = get_congestion_emoji(congestion)
    level = get_congestion_level(congestion)
    
    # HTML 스타일로 색상이 적용된 카드 렌더링
    st.markdown(f"""
    <div style="
        padding: 20px;
        border-radius: 10px;
        background: linear-gradient(135deg, {color}22 0%, {color}44 100%);
        border-left: 5px solid {color};
        margin-bottom: 10px;
    ">
        <p style="margin: 0; font-size: 14px; color: #666;">{label}</p>
        <p style="margin: 5px 0; font-size: 32px; font-weight: bold; color: {color};">{emoji} {value}</p>
        <p style="margin: 0; font-size: 12px; color: #888;">{level}</p>
    </div>
    """, unsafe_allow_html=True)
    
    if help_text:
        st.caption(help_text)


def render_congestion_legend():
    """
    혼잡 등급 범례를 렌더링합니다.
    """
    st.markdown("### 📊 혼잡 등급 안내")
    
    cols = st.columns(len(CONGESTION_LEVELS))
    
    for idx, (level_name, (min_val, max_val, color, emoji)) in enumerate(CONGESTION_LEVELS.items()):
        with cols[idx]:
            max_display = "+" if max_val == float('inf') else str(int(max_val))
            range_text = f"{int(min_val)}-{max_display}"
            
            st.markdown(f"""
            <div style="
                padding: 15px;
                border-radius: 8px;
                background-color: {color}22;
                border: 2px solid {color};
                text-align: center;
            ">
                <div style="font-size: 32px;">{emoji}</div>
                <div style="font-weight: bold; color: {color}; margin: 5px 0;">{level_name}</div>
                <div style="font-size: 12px; color: #666;">{range_text}</div>
            </div>
            """, unsafe_allow_html=True)


def suggest_alternatives(df: pd.DataFrame, line: str, direction: str):
    """
    빈 결과일 때 대안을 제안합니다.
    
    Args:
        df: 전체 데이터프레임
        line: 선택한 호선
        direction: 선택한 방향
    """
    # 해당 호선의 다른 역 목록
    available_stations = df[
        (df['line'] == line) & 
        (df['direction'] == direction)
    ]['station_name'].unique()
    
    if len(available_stations) > 0:
        st.info(f"💡 **{line} {direction} 방향**에서 선택 가능한 역: {', '.join(sorted(available_stations)[:5])} 등 {len(available_stations)}개")


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
    
    # 3. 내선/외선 방향 제외 (상행/하행만 유지)
    df_processed = df_processed[~df_processed['direction'].isin(['내선', '외선'])]
    
    return df_processed


# ============================================================================
# 페이즈 2: 필터 및 집계 함수
# ============================================================================

@st.cache_data
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


@st.cache_data
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
# 페이즈 3: 비교 분석 함수
# ============================================================================

# 시간대 프리셋 정의
TIME_PRESETS = {
    "출근": ("07:00", "09:00"),
    "퇴근": ("18:00", "20:00"),
}


@st.cache_data
def filter_for_direction_compare(df: pd.DataFrame, day_type: str, line: str, 
                                  station: str, start_time: str, end_time: str) -> pd.DataFrame:
    """
    양방향 데이터를 필터링합니다 (방향 비교용).
    
    Args:
        df: 전처리된 DataFrame
        day_type: 요일구분
        line: 호선
        station: 역명
        start_time: 시작 시간
        end_time: 종료 시간
        
    Returns:
        양방향 데이터가 포함된 필터링된 DataFrame
    """
    filtered = df[
        (df['day_type'] == day_type) &
        (df['line'] == line) &
        (df['station_name'] == station) &
        (df['time_slot'] >= start_time) &
        (df['time_slot'] <= end_time)
    ].copy()
    
    return filtered


@st.cache_data
def filter_for_line_compare(df: pd.DataFrame, day_type: str, lines: tuple, 
                            direction: str, start_time: str, end_time: str) -> pd.DataFrame:
    """
    다중 호선 데이터를 필터링합니다 (호선별 비교용).
    
    Args:
        df: 전처리된 DataFrame
        day_type: 요일구분
        lines: 호선 튜플 (캐싱을 위해 tuple 사용)
        direction: 방향
        start_time: 시작 시간
        end_time: 종료 시간
        
    Returns:
        다중 호선 데이터가 포함된 필터링된 DataFrame
    """
    filtered = df[
        (df['day_type'] == day_type) &
        (df['line'].isin(lines)) &
        (df['direction'] == direction) &
        (df['time_slot'] >= start_time) &
        (df['time_slot'] <= end_time)
    ].copy()
    
    return filtered


def create_direction_compare_chart(df: pd.DataFrame, time_slots: list, 
                                   station: str, day_type: str) -> alt.Chart:
    """
    방향 비교 멀티라인 차트를 생성합니다 (기준선 포함).
    
    Args:
        df: 양방향 데이터 DataFrame
        time_slots: 전체 시간대 리스트
        station: 역명
        day_type: 요일구분
        
    Returns:
        Altair 차트 객체
    """
    # NaN 제외
    chart_data = df.dropna(subset=['congestion'])
    
    if len(chart_data) == 0:
        return None
    
    # 기본 멀티라인 차트
    line_chart = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('time_slot:N', 
                title='시간대',
                sort=time_slots,
                axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('congestion:Q', 
                title='혼잡도',
                scale=alt.Scale(domain=[0, max(chart_data['congestion'].max() * 1.1, 120)])),
        color=alt.Color('direction:N', 
                       title='방향',
                       scale=alt.Scale(scheme='category10')),
        tooltip=[
            alt.Tooltip('direction:N', title='방향'),
            alt.Tooltip('time_slot:N', title='시간대'),
            alt.Tooltip('congestion:Q', title='혼잡도', format='.1f')
        ]
    )
    
    # 혼잡 등급 기준선 추가
    reference_lines = pd.DataFrame({
        'threshold': [30, 60, 100],
        'label': ['여유 기준', '보통 혼잡 기준', '매우 혼잡 기준']
    })
    
    rule_chart = alt.Chart(reference_lines).mark_rule(strokeDash=[5, 5], opacity=0.3, color='gray').encode(
        y='threshold:Q',
        size=alt.value(1)
    )
    
    # 차트 합성
    chart = (line_chart + rule_chart).properties(
        title=f"{station} 방향별 비교 - {day_type}",
        height=400
    )
    
    return chart


def create_line_compare_chart(df: pd.DataFrame, time_slots: list, 
                              direction: str, day_type: str) -> alt.Chart:
    """
    호선별 비교 멀티라인 차트를 생성합니다 (기준선 포함).
    
    Args:
        df: 다중 호선 데이터 DataFrame
        time_slots: 전체 시간대 리스트
        direction: 방향
        day_type: 요일구분
        
    Returns:
        Altair 차트 객체
    """
    # NaN 제외하고 시간대별 호선별 평균 계산
    chart_data = df.dropna(subset=['congestion']).groupby(
        ['line', 'time_slot'], as_index=False
    )['congestion'].mean()
    
    if len(chart_data) == 0:
        return None
    
    # 기본 멀티라인 차트
    line_chart = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('time_slot:N', 
                title='시간대',
                sort=time_slots,
                axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('congestion:Q', 
                title='평균 혼잡도',
                scale=alt.Scale(domain=[0, max(chart_data['congestion'].max() * 1.1, 120)])),
        color=alt.Color('line:N', 
                       title='호선',
                       scale=alt.Scale(scheme='category10')),
        tooltip=[
            alt.Tooltip('line:N', title='호선'),
            alt.Tooltip('time_slot:N', title='시간대'),
            alt.Tooltip('congestion:Q', title='평균 혼잡도', format='.1f')
        ]
    )
    
    # 혼잡 등급 기준선 추가
    reference_lines = pd.DataFrame({
        'threshold': [30, 60, 100],
        'label': ['여유 기준', '보통 혼잡 기준', '매우 혼잡 기준']
    })
    
    rule_chart = alt.Chart(reference_lines).mark_rule(strokeDash=[5, 5], opacity=0.3, color='gray').encode(
        y='threshold:Q',
        size=alt.value(1)
    )
    
    # 차트 합성
    chart = (line_chart + rule_chart).properties(
        title=f"호선별 평균 혼잡도 비교 ({direction}) - {day_type}",
        height=400
    )
    
    return chart


# ============================================================================
# 메인 UI (페이즈 3: 비교 기능 확장)
# ============================================================================

def main():
    st.set_page_config(page_title="서울 지하철 혼잡도 대시보드", layout="wide")
    st.title("🚇 서울 지하철 혼잡도 대시보드")
    st.markdown("**페이즈 4 완료**: UX/성능/안정화 - 혼잡 등급 색상, 기준선, 캐싱 최적화 적용")
    
    # 간단한 사용 안내
    st.info("""
    💡 **빠른 시작**: 왼쪽 사이드바에서 역과 시간대를 선택하세요. 
    출근/퇴근 시간대 프리셋을 사용하거나 여러 호선을 선택하여 비교할 수 있습니다.
    """)
    
    # 데이터 해석 안내
    with st.expander("ℹ️ 데이터 해석 가이드"):
        st.markdown("""
        ### 📊 혼잡도 값의 의미
        - 혼잡도는 지하철 칸의 승객 밀집도를 나타내는 지표입니다.
        - **100 이상**: 정원 초과 상태 (매우 혼잡)
        - **60-100**: 일부 승객이 서서 탑승 (보통 혼잡)
        - **30-60**: 대부분 착석 가능 (여유)
        - **0-30**: 충분한 좌석 여유 (매우 여유)
        
        ### ⏰ 시간대 표기 방법
        - 표기된 시간(예: "05:30")은 해당 시간부터 **30분 구간의 평균 혼잡도**를 나타냅니다.
        - 예: "07:00" = 07:00~07:30 구간, "08:30" = 08:30~09:00 구간
        
        ### ⚠️ 결측값(0.0 또는 빈 값) 해석
        - **0.0 값**: 해당 시간대에 미운행하거나 데이터 미집계
        - **빈 값**: 데이터 수집 오류 또는 해당 구간 없음
        - 심야/새벽 시간대에 0.0이 많은 것은 정상입니다.
        """)
    
    
    # 데이터 파일 경로
    data_file = "서울교통공사_지하철혼잡도정보_20250930.csv"
    
    # 파일 존재 여부 확인
    if not Path(data_file).exists():
        st.error(f"❌ 데이터 파일을 찾을 수 없습니다: `{data_file}`")
        st.info("💡 현재 디렉토리에 CSV 파일이 있는지 확인해주세요.")
        
        # 파일 업로드 옵션 제공
        st.markdown("### 📤 파일 업로드")
        uploaded_file = st.file_uploader(
            "혼잡도 CSV 파일을 업로드하세요",
            type=['csv'],
            help="서울교통공사 지하철 혼잡도 정보 CSV 파일"
        )
        
        if uploaded_file is not None:
            st.success(f"✅ 파일이 업로드되었습니다: {uploaded_file.name}")
            st.info("파일을 작업 디렉토리에 저장한 후 다시 실행해주세요.")
        
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
        
        st.markdown("**⏰ 시간대 프리셋**")
        col_preset1, col_preset2, col_preset3 = st.columns(3)
        
        with col_preset1:
            if st.button("출근", use_container_width=True):
                st.session_state['time_range'] = TIME_PRESETS["출근"]
        
        with col_preset2:
            if st.button("퇴근", use_container_width=True):
                st.session_state['time_range'] = TIME_PRESETS["퇴근"]
        
        with col_preset3:
            if st.button("전체", use_container_width=True):
                st.session_state['time_range'] = (time_slots[0], time_slots[-1])
        
        # 기본값 설정 (session_state가 없는 경우)
        if 'time_range' not in st.session_state:
            st.session_state['time_range'] = (time_slots[0], time_slots[-1])
        
        st.markdown("**시간대 범위**")
        start_time, end_time = st.select_slider(
            "시간대 선택",
            options=time_slots,
            value=st.session_state['time_range'],
            key='time_slider'
        )
        
        # session_state 업데이트
        st.session_state['time_range'] = (start_time, end_time)
        
        st.markdown("---")
        st.markdown("**🚇 호선별 비교**")
        compare_lines = st.multiselect(
            "비교할 호선 선택",
            options=lines,
            default=[selected_line] if selected_line in lines else [],
            help="여러 호선을 선택하여 혼잡도를 비교할 수 있습니다."
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
    
    # 빈 결과 처리 - 대안 제안 추가
    if len(filtered_df) == 0:
        st.warning("⚠️ 선택한 조건에 해당하는 데이터가 없습니다.")
        st.info("💡 **대안 제안**: 시간대 범위를 넓히거나 다른 역/호선을 선택해보세요.")
        
        # 대안 제안
        suggest_alternatives(df, selected_line, selected_direction)
        
        # 추가 팁
        with st.expander("📌 문제 해결 팁"):
            st.markdown("""
            **데이터가 없는 경우 확인 사항:**
            1. **시간대 범위**: 너무 좁은 시간대를 선택하지 않았는지 확인하세요.
            2. **요일구분**: 현재 데이터는 평일만 포함할 수 있습니다.
            3. **역/방향**: 선택한 역과 방향 조합이 실제로 운행되는지 확인하세요.
            
            **추천 조치:**
            - "전체" 시간대 프리셋 버튼을 클릭해보세요.
            - 다른 역을 선택해보세요.
            - 다른 방향을 선택해보세요.
            """)
        
        st.stop()
    
    # ========================================================================
    # KPI 카드 (3개) - 혼잡 등급별 색상 적용
    # ========================================================================
    kpis = calculate_kpis(filtered_df)
    
    # 혼잡 등급 범례 표시
    render_congestion_legend()
    st.markdown("---")
    
    st.markdown("### 📊 핵심 지표")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        render_kpi_with_color(
            label="최대 혼잡도",
            value=f"{kpis['max_congestion']:.1f}",
            congestion=kpis['max_congestion'],
            help_text="선택한 시간대 내 최대 혼잡도"
        )
    
    with col2:
        # 피크 시간대는 색상 없이 표시
        st.markdown(f"""
        <div style="
            padding: 20px;
            border-radius: 10px;
            background: linear-gradient(135deg, #95a5a622 0%, #95a5a644 100%);
            border-left: 5px solid #95a5a6;
            margin-bottom: 10px;
        ">
            <p style="margin: 0; font-size: 14px; color: #666;">피크 시간대</p>
            <p style="margin: 5px 0; font-size: 32px; font-weight: bold; color: #95a5a6;">⏰ {kpis['peak_time']}</p>
            <p style="margin: 0; font-size: 12px; color: #888;">최대 혼잡도 발생 시각</p>
        </div>
        """, unsafe_allow_html=True)
        st.caption("최대 혼잡도가 발생한 시간")
    
    with col3:
        render_kpi_with_color(
            label="평균 혼잡도",
            value=f"{kpis['avg_congestion']:.1f}",
            congestion=kpis['avg_congestion'],
            help_text="선택한 시간대 내 평균 혼잡도"
        )
    
    st.markdown("---")
    
    # ========================================================================
    # 라인차트 (시간대별 혼잡도) - 기준선 추가
    # ========================================================================
    st.markdown("### 📈 시간대별 혼잡도 추이")
    
    # 대용량 데이터 경고
    if len(filtered_df) > 10000:
        st.warning(f"⚠️ 대용량 데이터 ({len(filtered_df):,}개 레코드) - 차트 생성에 시간이 걸릴 수 있습니다.")
    
    # NaN 제외한 데이터로 차트 생성
    chart_data = filtered_df.dropna(subset=['congestion'])
    
    if len(chart_data) > 0:
        with st.spinner("📊 차트를 생성하는 중..."):
            # 기본 라인 차트
            line_chart = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3, color='#1f77b4').encode(
                x=alt.X('time_slot:N', 
                        title='시간대',
                        sort=time_slots,
                        axis=alt.Axis(labelAngle=-45)),
                y=alt.Y('congestion:Q', 
                        title='혼잡도',
                        scale=alt.Scale(domain=[0, max(chart_data['congestion'].max() * 1.1, 120)])),
                tooltip=[
                    alt.Tooltip('time_slot:N', title='시간대'),
                    alt.Tooltip('congestion:Q', title='혼잡도', format='.1f')
                ]
            )
            
            # 혼잡 등급 기준선 추가
            reference_lines = pd.DataFrame({
                'threshold': [30, 60, 100],
                'label': ['여유 기준', '보통 혼잡 기준', '매우 혼잡 기준'],
                'color': ['#2ecc71', '#f1c40f', '#e74c3c']
            })
            
            rule_chart = alt.Chart(reference_lines).mark_rule(strokeDash=[5, 5], opacity=0.5).encode(
                y='threshold:Q',
                color=alt.Color('label:N', scale=alt.Scale(
                    domain=['여유 기준', '보통 혼잡 기준', '매우 혼잡 기준'],
                    range=['#2ecc71', '#f1c40f', '#e74c3c']
                ), legend=alt.Legend(title='기준선')),
                size=alt.value(2)
            )
            
            # 차트 합성
            final_chart = (line_chart + rule_chart).properties(
                title=f"{selected_station} ({selected_direction}) - {selected_day}",
                height=400
            )
            
            st.altair_chart(final_chart, use_container_width=True)
        
        # 안내 캡션
        col_caption1, col_caption2 = st.columns(2)
        with col_caption1:
            st.caption("💡 점선은 혼잡 등급 기준선입니다. (30: 여유, 60: 보통 혼잡, 100: 매우 혼잡)")
        with col_caption2:
            # 결측값 비율 표시
            total_count = len(filtered_df)
            missing_count = filtered_df['congestion'].isna().sum()
            if missing_count > 0:
                missing_pct = (missing_count / total_count * 100)
                st.caption(f"⚠️ 결측값: {missing_count}개 ({missing_pct:.1f}%) - 미운행 또는 미집계 시간대")
    else:
        st.info("표시할 데이터가 없습니다.")
    
    st.markdown("---")
    
    # ========================================================================
    # 방향 비교 차트 (페이즈 3)
    # ========================================================================
    st.markdown("### ⚖️ 방향별 혼잡도 비교")
    
    # 양방향 데이터 필터링
    with st.spinner("🔄 방향별 데이터를 비교하는 중..."):
        direction_compare_df = filter_for_direction_compare(
            df, 
            selected_day, 
            selected_line, 
            selected_station,
            start_time, 
            end_time
        )
    
    if len(direction_compare_df) > 0:
        with st.spinner("📊 비교 차트를 생성하는 중..."):
            direction_chart = create_direction_compare_chart(
                direction_compare_df, 
                time_slots, 
                selected_station, 
                selected_day
            )
        
        if direction_chart is not None:
            st.altair_chart(direction_chart, use_container_width=True)
            st.caption("💡 선택한 역의 양방향 혼잡도를 비교합니다. 출근/퇴근 시간대에 방향별 차이가 명확히 나타납니다.")
        else:
            st.info("방향별 비교 데이터가 없습니다.")
    else:
        st.info("선택한 조건에 해당하는 방향별 데이터가 없습니다.")
    
    st.markdown("---")
    
    # ========================================================================
    # 호선별 비교 차트 (페이즈 3)
    # ========================================================================
    if len(compare_lines) > 0:
        st.markdown("### 🚇 호선별 평균 혼잡도 비교")
        
        # 다중 호선 데이터 필터링 (캐싱을 위해 tuple로 변환)
        with st.spinner(f"🚇 {len(compare_lines)}개 호선 데이터를 비교하는 중..."):
            line_compare_df = filter_for_line_compare(
                df, 
                selected_day, 
                tuple(compare_lines), 
                selected_direction,
                start_time, 
                end_time
            )
        
        if len(line_compare_df) > 0:
            # 대용량 비교 데이터 경고
            if len(line_compare_df) > 5000:
                st.info(f"ℹ️ {len(line_compare_df):,}개 레코드를 집계하여 차트를 생성합니다.")
            
            with st.spinner("📊 호선별 비교 차트를 생성하는 중..."):
                line_chart = create_line_compare_chart(
                    line_compare_df, 
                    time_slots, 
                    selected_direction, 
                    selected_day
                )
            
            if line_chart is not None:
                st.altair_chart(line_chart, use_container_width=True)
                
                # 추가 정보 표시
                col_caption1, col_caption2 = st.columns(2)
                with col_caption1:
                    st.caption("💡 각 호선의 전체 역 평균 혼잡도를 시간대별로 비교합니다.")
                with col_caption2:
                    unique_lines_in_result = line_compare_df['line'].nunique()
                    if unique_lines_in_result < len(compare_lines):
                        st.caption(f"⚠️ 선택한 {len(compare_lines)}개 호선 중 {unique_lines_in_result}개 호선의 데이터만 표시됩니다.")
            else:
                st.info("호선별 비교 데이터가 없습니다.")
        else:
            st.info("선택한 조건에 해당하는 호선별 데이터가 없습니다.")
        
        st.markdown("---")
    
    # ========================================================================
    # TOP 구간 테이블 + CSV 다운로드 (페이즈 3: 기준 선택)
    # ========================================================================
    st.markdown("### 🔝 혼잡 TOP 10 구간")
    
    # TOP N 정렬 기준 선택
    col_top1, col_top2 = st.columns([2, 1])
    
    with col_top1:
        top_criteria = st.radio(
            "정렬 기준",
            options=["피크 (최대)", "평균", "특정 시간대"],
            horizontal=True,
            help="혼잡 TOP 구간을 선택한 기준으로 정렬합니다."
        )
    
    with col_top2:
        if top_criteria == "특정 시간대":
            specific_time = st.selectbox(
                "시간대 선택",
                options=time_slots,
                index=time_slots.index("08:00") if "08:00" in time_slots else 0
            )
    
    # 혼잡 TOP 10 구간 계산
    top_n = 10
    
    if top_criteria == "피크 (최대)":
        # 기존 방식: 각 시간대별 최대값
        top_df = filtered_df.dropna(subset=['congestion']).nlargest(top_n, 'congestion')[
            ['time_slot', 'station_name', 'line', 'direction', 'congestion']
        ].reset_index(drop=True)
    
    elif top_criteria == "평균":
        # 역/방향별 평균 혼잡도로 정렬
        avg_df = filtered_df.dropna(subset=['congestion']).groupby(
            ['station_name', 'line', 'direction'], as_index=False
        )['congestion'].mean()
        avg_df = avg_df.rename(columns={'congestion': 'avg_congestion'})
        top_df = avg_df.nlargest(top_n, 'avg_congestion')[
            ['station_name', 'line', 'direction', 'avg_congestion']
        ].reset_index(drop=True)
        top_df = top_df.rename(columns={'avg_congestion': 'congestion'})
        top_df.insert(1, 'time_slot', '평균')
    
    else:  # 특정 시간대
        # 특정 시간대의 혼잡도로 정렬
        time_specific_df = filtered_df[
            filtered_df['time_slot'] == specific_time
        ].dropna(subset=['congestion'])
        top_df = time_specific_df.nlargest(top_n, 'congestion')[
            ['time_slot', 'station_name', 'line', 'direction', 'congestion']
        ].reset_index(drop=True)
    
    # 빈 결과 처리
    if len(top_df) == 0:
        st.info("선택한 조건에 해당하는 혼잡 데이터가 없습니다.")
    else:
        # 순위 추가
        top_df.insert(0, '순위', range(1, len(top_df) + 1))
        
        # 혼잡 등급 및 이모지 추가
        top_df['혼잡등급'] = top_df['congestion'].apply(get_congestion_emoji)
        
        # 컬럼명 한글화
        top_df_display = top_df.rename(columns={
            '순위': '순위',
            'time_slot': '시간대',
            'station_name': '역명',
            'line': '호선',
            'direction': '방향',
            'congestion': '혼잡도',
            '혼잡등급': '등급'
        })
        
        # 혼잡도에 색상 적용하는 함수
        def color_congestion(val):
            if pd.isna(val):
                return ''
            color = get_congestion_color(val)
            return f'background-color: {color}33; color: {color}; font-weight: bold;'
        
        # 스타일 적용
        styled_df = top_df_display.style.applymap(
            color_congestion,
            subset=['혼잡도']
        )
        
        st.dataframe(
            styled_df,
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
    with st.expander("ℹ️ 데이터 정보 및 사용 가이드"):
        st.markdown("### 📋 필터 조건")
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown(f"""
            **기본 필터:**
            - 요일구분: `{selected_day}`
            - 호선: `{selected_line}`
            - 역: `{selected_station}`
            - 방향: `{selected_direction}`
            """)
        
        with col_info2:
            st.markdown(f"""
            **시간대:**
            - 범위: `{start_time} ~ {end_time}`
            
            **비교 설정:**
            - 비교 호선: `{', '.join(compare_lines) if compare_lines else '없음'}`
            """)
        
        st.markdown(f"**필터링된 데이터:** {len(filtered_df):,}개 레코드")
        
        st.markdown("---")
        st.markdown("### 📊 혼잡도 해석")
        st.markdown("""
        혼잡도는 지하철 칸의 혼잡 정도를 나타내는 지표입니다:
        
        | 혼잡도 범위 | 상태 | 설명 |
        |------------|------|------|
        | 100 이상 | 🔴 매우 혼잡 | 승객이 많아 불편할 수 있음 |
        | 60-100 | 🟡 보통 혼잡 | 일부 서서 가는 승객 있음 |
        | 30-60 | 🟢 여유 있음 | 대부분 앉아서 이동 가능 |
        | 0-30 | 🔵 매우 여유로움 | 충분한 좌석 여유 |
        
        **참고:** 0.0 값은 해당 시간대에 미운행 또는 미집계된 데이터일 수 있습니다.
        """)
        
        st.markdown("---")
        st.markdown("### 🎯 기능 가이드")
        st.markdown("""
        **시간대 프리셋:**
        - **출근**: 오전 7시~9시 구간
        - **퇴근**: 오후 6시~8시 구간
        - **전체**: 전체 운행 시간
        
        **비교 기능:**
        - **방향 비교**: 선택한 역의 상/하행(또는 내/외선) 혼잡도 비교
        - **호선별 비교**: 여러 호선의 평균 혼잡도를 시간대별로 비교
        
        **TOP N 정렬:**
        - **피크 (최대)**: 각 시간대별 최대 혼잡도 기준
        - **평균**: 선택 구간의 평균 혼잡도 기준
        - **특정 시간대**: 선택한 시간대의 혼잡도 기준
        """)


if __name__ == "__main__":
    main()
