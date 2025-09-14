# tools/profile_backtest.py
# -*- coding: utf-8 -*-
"""
백테스트 성능 프로파일링 스크립트 (cProfile 사용)
- run_backtest.py의 메인 로직을 실행하고 성능을 분석합니다.
- 결과는 outputs/profiling/ 디렉터리에 저장됩니다.
"""
import cProfile
import pstats
import os
import sys
from io import StringIO

# 프로젝트 루트를 sys.path에 추가하여 모듈 임포트 경로 문제 해결
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# run_backtest의 메인 함수를 임포트
# 스크립트의 구조에 따라 임포트 경로를 수정해야 할 수 있습니다.
try:
    from run_backtest import main as run_backtest_main
except ImportError as e:
    print(f"Error importing 'run_backtest'. Make sure it has a main() function. Details: {e}")
    sys.exit(1)

def profile_backtest():
    """
    cProfile을 사용하여 백테스트를 실행하고 성능 데이터를 수집합니다.
    """
    output_dir = os.path.join(project_root, 'outputs', 'profiling')
    os.makedirs(output_dir, exist_ok=True)
    
    profile_output_path = os.path.join(output_dir, 'backtest_performance.prof')
    
    print("백테스트 프로파일링을 시작합니다...")
    
    # cProfile 실행
    profiler = cProfile.Profile()
    profiler.enable()
    
    original_argv = sys.argv
    try:
        # run_backtest.py에 필요한 인자를 sys.argv를 통해 전달
        print("백테스트 인자 설정: --symbol BTC/USDT --start_date 2023-01-01")
        sys.argv = [
            'run_backtest.py',
            '--symbol', 'BTC/USDT',
            '--start_date', '2023-01-01'
        ]
        
        # run_backtest.py의 main 함수 실행
        run_backtest_main()
    finally:
        profiler.disable()
        sys.argv = original_argv # 원래 sys.argv로 복원
        print(f"프로파일링 완료. 결과 파일: {profile_output_path}")
        
        # 결과 저장
        profiler.dump_stats(profile_output_path)
        
    return profile_output_path

def analyze_profile(profile_path: str):
    """
    프로파일링 결과 파일을 분석하고 주요 병목 지점을 출력합니다.
    """
    output_dir = os.path.join(project_root, 'outputs', 'profiling')
    analysis_output_path = os.path.join(output_dir, 'backtest_analysis.txt')
    
    print(f"\n프로파일링 결과 분석 ({profile_path}):")
    
    # StringIO를 사용하여 출력을 문자열로 캡처
    s = StringIO()
    stats = pstats.Stats(profile_path, stream=s)
    
    # 가장 많은 누적 시간을 소요한 함수 상위 20개
    stats.sort_stats(pstats.SortKey.CUMULATIVE).print_stats(20)
    
    # 가장 많은 내부 시간을 소요한 함수 상위 20개
    stats.sort_stats(pstats.SortKey.TIME).print_stats(20)
    
    analysis_result = s.getvalue()
    
    # 터미널에 분석 결과 출력
    print(analysis_result)
    
    # 파일에 분석 결과 저장
    with open(analysis_output_path, 'w', encoding='utf-8') as f:
        f.write("백테스트 성능 분석 결과\n")
        f.write("="*30 + "\n\n")
        f.write(analysis_result)
        
    print(f"분석 리포트가 다음 파일에 저장되었습니다: {analysis_output_path}")

if __name__ == "__main__":
    # 1. 프로파일링 실행
    prof_file = profile_backtest()
    
    # 2. 결과 분석
    if os.path.exists(prof_file):
        analyze_profile(prof_file)
    else:
        print("프로파일링 결과 파일이 생성되지 않았습니다.")
