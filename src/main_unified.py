# -*- coding: utf-8 -*-
import asyncio
import sys
import psutil
import signal
from multiprocessing import freeze_support
from loguru import logger
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file at the very beginning
load_dotenv(find_dotenv())

# **안전장치: 시스템 리소스 모니터링 클래스**
class SystemMonitor:
    def __init__(self, cpu_threshold=80, memory_threshold=80):
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.process = psutil.Process()
        
    def check_system_health(self):
        """시스템 리소스 상태를 확인하고 임계값 초과 시 경고"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            if cpu_percent > self.cpu_threshold:
                logger.warning(f"⚠️ CPU 사용률 높음: {cpu_percent:.1f}% (임계값: {self.cpu_threshold}%)")
                return False
                
            if memory_percent > self.memory_threshold:
                logger.warning(f"⚠️ 메모리 사용률 높음: {memory_percent:.1f}% (임계값: {self.memory_threshold}%)")
                return False
                
            logger.info(f"시스템 상태 양호 - CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%")
            return True
            
        except Exception as e:
            logger.error(f"시스템 모니터링 오류: {e}")
            return True  # 오류 시에는 계속 진행

async def run_all():
    """거래 엔진과 텔레그램 봇 리스너를 별도의 프로세스로 실행합니다."""
    logger.info("통합 봇 시스템을 시작합니다...")
    
    # **안전장치: 시스템 모니터 초기화 (임계값 조정)**
    monitor = SystemMonitor(cpu_threshold=90, memory_threshold=90)  # 85% → 90%로 완화
    
    # **안전장치: 초기 시스템 상태 확인**
    if not monitor.check_system_health():
        logger.error("❌ 초기 시스템 상태가 좋지 않아 봇을 시작할 수 없습니다.")
        return

    # 현재 Python 실행 파일을 사용하여 자식 프로세스를 실행
    python_executable = sys.executable
    
    # 각 모듈을 독립적으로 실행하도록 명령어 정의
    # -u 플래그는 unbuffered output을 보장하여 로그가 즉시 표시되도록 함
    cmd_engine = [python_executable, "-u", "-m", "src.engine.main_realtime"]
    cmd_listener = [python_executable, "-u", "-m", "src.notifier.bot_listener"]

    process_engine = None
    process_listener = None

    try:
        # **안전장치: 시스템 상태 재확인**
        if not monitor.check_system_health():
            logger.error("❌ 프로세스 시작 전 시스템 상태 불량")
            return

        # 거래 엔진 프로세스 시작
        process_engine = await asyncio.create_subprocess_exec(
            *cmd_engine,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        logger.info(f"거래 엔진 프로세스 시작 (PID: {process_engine.pid})")

        # **안전장치: 프로세스 시작 후 짧은 대기**
        await asyncio.sleep(3)

        # 텔레그램 리스너 프로세스 시작
        process_listener = await asyncio.create_subprocess_exec(
            *cmd_listener,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        logger.info(f"텔레그램 리스너 프로세스 시작 (PID: {process_listener.pid})")

        # **안전장치: 주기적 시스템 모니터링**
        monitoring_task = asyncio.create_task(monitor_system_periodically(monitor, process_engine, process_listener))

        # 두 프로세스가 모두 종료될 때까지 대기
        await asyncio.gather(
            process_engine.wait(),
            process_listener.wait(),
            monitoring_task
        )

    except asyncio.CancelledError:
        logger.info("메인 프로세스가 중단 신호를 수신했습니다.")
    except Exception as e:
        logger.exception(f"프로세스 실행 중 오류 발생: {e}")
    finally:
        logger.info("모든 하위 프로세스를 안전하게 종료합니다...")
        
        # **안전장치: 강제 종료 전에 정상 종료 시도**
        if process_engine and process_engine.returncode is None:
            try:
                process_engine.terminate()
                await asyncio.wait_for(process_engine.wait(), timeout=10.0)
                logger.info("거래 엔진 프로세스가 정상 종료되었습니다.")
            except asyncio.TimeoutError:
                logger.warning("거래 엔진 프로세스 강제 종료를 시도합니다.")
                try:
                    process_engine.kill()
                    await process_engine.wait()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                logger.info("거래 엔진 프로세스가 이미 종료되었습니다.")
                
        if process_listener and process_listener.returncode is None:
            try:
                process_listener.terminate()
                await asyncio.wait_for(process_listener.wait(), timeout=10.0)
                logger.info("텔레그램 리스너 프로세스가 정상 종료되었습니다.")
            except asyncio.TimeoutError:
                logger.warning("텔레그램 리스너 프로세스 강제 종료를 시도합니다.")
                try:
                    process_listener.kill()
                    await process_listener.wait()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                logger.info("텔레그램 리스너 프로세스가 이미 종료되었습니다.")
                
        logger.info("통합 봇 시스템을 종료합니다.")

async def monitor_system_periodically(monitor: SystemMonitor, process_engine, process_listener):
    """주기적으로 시스템 상태를 모니터링하고 위험 시 프로세스를 종료"""
    consecutive_warnings = 0
    max_consecutive_warnings = 3
    
    while True:
        try:
            await asyncio.sleep(30)  # 30초마다 모니터링
            
            if monitor.check_system_health():
                consecutive_warnings = 0
            else:
                consecutive_warnings += 1
                logger.warning(f"시스템 상태 경고 {consecutive_warnings}/{max_consecutive_warnings}")
                
                if consecutive_warnings >= max_consecutive_warnings:
                    logger.error("❌ 연속 시스템 경고로 인한 안전 종료를 시작합니다.")
                    
                    # 프로세스 안전 종료
                    if process_engine and process_engine.returncode is None:
                        process_engine.terminate()
                    if process_listener and process_listener.returncode is None:
                        process_listener.terminate()
                    break
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"시스템 모니터링 중 오류: {e}")
            await asyncio.sleep(30)

def main():
    """메인 진입점."""
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logger.exception(f"최상위 레벨에서 처리되지 않은 예외: {e}")
    sys.exit(0)

if __name__ == "__main__":
    # Windows에서 멀티프로세싱 문제를 방지하기 위해 필수
    freeze_support()
    main()
