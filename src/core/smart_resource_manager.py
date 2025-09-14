# -*- coding: utf-8 -*-
"""
스마트 로드 밸런싱 및 캐싱 매니저

- 목적: 시스템 리소스 효율적 활용 및 성능 최적화
- 핵심 기능:
  1) 적응형 워커 수 조절: CPU/메모리 사용률에 따른 동적 스케일링
  2) 인텔리전트 캐싱: 중복 계산 방지 및 메모리 효율성
  3) 비동기 작업 큐: 우선순위 기반 작업 처리
  4) 리소스 모니터링: 실시간 성능 지표 추적
"""
from __future__ import annotations
import asyncio
import psutil
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import logging
from functools import wraps

logger = logging.getLogger(__name__)

@dataclass
class SystemMetrics:
    """시스템 성능 지표"""
    cpu_percent: float
    memory_percent: float
    active_workers: int
    queue_size: int
    cache_hit_rate: float
    timestamp: float = field(default_factory=time.time)

@dataclass 
class TaskItem:
    """작업 항목"""
    func: Callable
    args: tuple
    kwargs: dict
    priority: int = 5  # 1-10 (1이 최고 우선순위)
    task_id: str = ""
    submitted_at: float = field(default_factory=time.time)

class SmartResourceManager:
    """스마트 리소스 관리자"""
    
    def __init__(self, 
                 min_workers: int = 1, 
                 max_workers: int = 4,
                 cpu_threshold: float = 80.0,
                 memory_threshold: float = 80.0):
        
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        
        self.current_workers = min_workers
        self.executor: Optional[ProcessPoolExecutor] = None
        
        # 성능 메트릭 추적
        self.metrics_history: deque = deque(maxlen=60)  # 최근 60개 메트릭
        self.task_queue: deque = deque()  # 우선순위 작업 큐
        
        # 캐시 통계
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "total_requests": 0
        }
        
        self.is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """리소스 매니저 시작"""
        if self.is_running:
            return
            
        self.is_running = True
        self._create_executor()
        
        # 모니터링 태스크 시작
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"스마트 리소스 매니저 시작 - 워커 수: {self.current_workers}")
        
    async def stop(self):
        """리소스 매니저 종료"""
        self.is_running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None
            
        logger.info("스마트 리소스 매니저 종료")
        
    def _create_executor(self):
        """ProcessPoolExecutor 생성"""
        if self.executor:
            self.executor.shutdown(wait=False)
            
        import multiprocessing
        mp_context = multiprocessing.get_context('spawn')
        
        self.executor = ProcessPoolExecutor(
            max_workers=self.current_workers,
            mp_context=mp_context
        )
        
    async def _monitor_loop(self):
        """시스템 모니터링 루프"""
        while self.is_running:
            try:
                # 시스템 메트릭 수집
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent
                
                # 캐시 히트율 계산
                total_requests = self.cache_stats["total_requests"]
                cache_hit_rate = (
                    self.cache_stats["hits"] / total_requests * 100 
                    if total_requests > 0 else 0
                )
                
                # 메트릭 저장
                metrics = SystemMetrics(
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    active_workers=self.current_workers,
                    queue_size=len(self.task_queue),
                    cache_hit_rate=cache_hit_rate
                )
                self.metrics_history.append(metrics)
                
                # 동적 스케일링 결정
                await self._adjust_workers(metrics)
                
                await asyncio.sleep(10)  # 10초마다 모니터링
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"모니터링 루프 오류: {e}")
                await asyncio.sleep(10)
                
    async def _adjust_workers(self, metrics: SystemMetrics):
        """워커 수 동적 조절"""
        try:
            # 최근 3개 메트릭의 평균 계산
            recent_metrics = list(self.metrics_history)[-3:]
            if len(recent_metrics) < 2:
                return
                
            avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
            avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
            avg_queue_size = sum(m.queue_size for m in recent_metrics) / len(recent_metrics)
            
            old_workers = self.current_workers
            
            # 스케일 업 조건
            if (avg_queue_size > 2 and 
                avg_cpu < self.cpu_threshold - 10 and 
                avg_memory < self.memory_threshold - 10 and
                self.current_workers < self.max_workers):
                
                self.current_workers = min(self.max_workers, self.current_workers + 1)
                
            # 스케일 다운 조건
            elif ((avg_cpu > self.cpu_threshold or avg_memory > self.memory_threshold) and
                  self.current_workers > self.min_workers):
                
                self.current_workers = max(self.min_workers, self.current_workers - 1)
                
            # 유휴 상태에서 스케일 다운
            elif (avg_queue_size == 0 and 
                  avg_cpu < 30 and 
                  self.current_workers > self.min_workers):
                
                self.current_workers = max(self.min_workers, self.current_workers - 1)
            
            # 워커 수 변경시 executor 재생성
            if old_workers != self.current_workers:
                logger.info(f"워커 수 조절: {old_workers} → {self.current_workers} "
                          f"(CPU: {avg_cpu:.1f}%, Memory: {avg_memory:.1f}%, Queue: {avg_queue_size:.1f})")
                self._create_executor()
                
        except Exception as e:
            logger.error(f"워커 수 조절 오류: {e}")
            
    async def submit_task(self, 
                         func: Callable,
                         *args, 
                         priority: int = 5,
                         task_id: str = "",
                         **kwargs) -> Any:
        """우선순위 기반 작업 제출"""
        if not self.executor:
            raise RuntimeError("리소스 매니저가 시작되지 않았습니다.")
            
        task = TaskItem(
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            task_id=task_id or f"task_{int(time.time()*1000)}"
        )
        
        # 우선순위에 따라 큐에 삽입
        inserted = False
        for i, existing_task in enumerate(self.task_queue):
            if task.priority < existing_task.priority:  # 낮은 숫자가 높은 우선순위
                self.task_queue.insert(i, task)
                inserted = True
                break
                
        if not inserted:
            self.task_queue.append(task)
            
        # 작업 실행
        return await self._execute_next_task()
        
    async def _execute_next_task(self) -> Any:
        """다음 작업 실행"""
        if not self.task_queue:
            return None
            
        task = self.task_queue.popleft()
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self.executor, 
                task.func, 
                *task.args, 
                **task.kwargs
            )
            
            execution_time = time.time() - task.submitted_at
            logger.debug(f"작업 완료: {task.task_id} (실행시간: {execution_time:.2f}초)")
            
            return result
            
        except Exception as e:
            logger.error(f"작업 실행 오류: {task.task_id} - {e}")
            raise
            
    def update_cache_stats(self, hit: bool):
        """캐시 통계 업데이트"""
        self.cache_stats["total_requests"] += 1
        if hit:
            self.cache_stats["hits"] += 1
        else:
            self.cache_stats["misses"] += 1
            
    def get_metrics(self) -> Dict[str, Any]:
        """현재 성능 지표 반환"""
        if not self.metrics_history:
            return {}
            
        latest = self.metrics_history[-1]
        return {
            "cpu_percent": latest.cpu_percent,
            "memory_percent": latest.memory_percent,
            "active_workers": latest.active_workers,
            "queue_size": latest.queue_size,
            "cache_hit_rate": latest.cache_hit_rate,
            "cache_stats": self.cache_stats.copy(),
            "uptime": time.time() - (self.metrics_history[0].timestamp if self.metrics_history else time.time())
        }
        
    def get_executor(self) -> ProcessPoolExecutor:
        """현재 executor 반환"""
        if not self.executor:
            raise RuntimeError("리소스 매니저가 시작되지 않았습니다.")
        return self.executor

# --- 데코레이터: 캐시된 작업 실행 ---
def cached_task(priority: int = 5):
    """캐시된 작업 실행 데코레이터"""
    def decorator(func):
        @wraps(func)
        async def wrapper(resource_manager: SmartResourceManager, *args, **kwargs):
            # 캐시 키 생성
            cache_key = f"{func.__name__}_{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # 캐시 조회 (실제 구현에서는 Redis 등 사용)
            # 여기서는 단순화를 위해 메모리 기반 캐시 시뮬레이션
            cached_result = getattr(wrapper, '_cache', {}).get(cache_key)
            
            if cached_result:
                resource_manager.update_cache_stats(hit=True)
                logger.debug(f"캐시 히트: {cache_key}")
                return cached_result
                
            # 캐시 미스 - 실제 작업 실행
            resource_manager.update_cache_stats(hit=False)
            result = await resource_manager.submit_task(func, *args, priority=priority, **kwargs)
            
            # 캐시 저장 (최대 100개 항목)
            if not hasattr(wrapper, '_cache'):
                wrapper._cache = {}
            
            if len(wrapper._cache) >= 100:
                # LRU 방식으로 오래된 항목 제거
                oldest_key = next(iter(wrapper._cache))
                del wrapper._cache[oldest_key]
                
            wrapper._cache[cache_key] = result
            return result
            
        return wrapper
    return decorator

# --- 전역 리소스 매니저 인스턴스 ---
_resource_manager: Optional[SmartResourceManager] = None

def get_resource_manager() -> SmartResourceManager:
    """전역 리소스 매니저 인스턴스 반환"""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = SmartResourceManager(
            min_workers=1,
            max_workers=min(4, psutil.cpu_count() // 2),  # 전체 코어의 절반만 사용
            cpu_threshold=85.0,
            memory_threshold=85.0
        )
    return _resource_manager