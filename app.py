import streamlit as st
import pandas as pd
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
# 메인 UI
# ============================================================================

def main():
    st.title("서울 지하철 혼잡도 대시보드")
    st.markdown("**페이즈 1**: 데이터 로드 및 전처리 확인")
    
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
    
    st.success(f"데이터 로드 완료! 총 {len(df):,}개 레코드")
    
    # 품질 검사 리포트
    with st.expander("📊 데이터 품질 리포트", expanded=True):
        report = get_data_quality_report(df)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("총 레코드 수", f"{report['total_records']:,}")
            st.metric("유니크 역", f"{report['unique_stations']}")
            st.metric("유니크 호선", f"{report['unique_lines']}")
        
        with col2:
            st.metric("결측치", f"{report['total_missing']:,}", 
                     f"{report['missing_pct']:.2f}%")
            st.metric("0.0 값", f"{report['zero_count']:,}",
                     f"{report['zero_pct']:.2f}%")
            st.metric("음수 값", f"{report['negative_count']}")
        
        with col3:
            if report['mean_congestion'] is not None:
                st.metric("평균 혼잡도", f"{report['mean_congestion']:.1f}")
                st.metric("최대 혼잡도", f"{report['max_congestion']:.1f}")
                st.metric("100 초과 값", f"{report['over_100_count']:,}")
        
        # 상세 통계
        st.markdown("---")
        st.markdown("**상세 통계**")
        stats_col1, stats_col2 = st.columns(2)
        
        with stats_col1:
            st.write(f"- 최소 혼잡도: {report['min_congestion']:.1f}" if report['min_congestion'] is not None else "- 최소 혼잡도: N/A")
            st.write(f"- 중앙값 혼잡도: {report['median_congestion']:.1f}" if report['median_congestion'] is not None else "- 중앙값 혼잡도: N/A")
        
        with stats_col2:
            st.write(f"- 요일구분 종류: {report['unique_day_types']}")
            st.write(f"- 데이터 품질: {'✅ 양호' if report['negative_count'] == 0 else '⚠️ 음수 값 존재'}")
    
    # 샘플 데이터 표시
    st.markdown("---")
    st.subheader("🔍 전처리 결과 샘플 (20행)")
    
    # 샘플 20행 표시
    st.dataframe(
        df.head(20),
        width='stretch',
        height=400
    )
    
    # 전체 데이터 스키마 정보
    with st.expander("📋 데이터 스키마"):
        st.write("**컬럼 정보:**")
        schema_df = pd.DataFrame({
            '컬럼명': df.columns,
            '타입': [str(df[col].dtype) for col in df.columns],
            '샘플': [str(df[col].iloc[0]) if len(df) > 0 else '' for col in df.columns]
        })
        st.dataframe(schema_df, width='stretch')


if __name__ == "__main__":
    main()
