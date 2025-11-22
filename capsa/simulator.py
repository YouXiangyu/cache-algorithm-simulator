from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .cache_base import Cache


@dataclass
class SimulationResult:
    """一次运行后的模拟统计信息，将由MetricsCollector渲染。"""

    algorithm: str
    cache_size: int
    total_requests: int
    hits: int
    misses: int
    elapsed_ns: int
    cache_stats: Dict[str, int]

    @property
    def hit_rate(self) -> float:
        """命中率（命中数 / 总请求数），以百分比返回。"""
        return (self.hits / self.total_requests) * 100 if self.total_requests else 0.0

    @property
    def avg_overhead_ns(self) -> float:
        """平均计算开销，显示算法复杂度而非实际I/O时间。"""
        return self.elapsed_ns / self.total_requests if self.total_requests else 0.0


class Simulator:
    """简单模拟器：顺序读取跟踪序列，提供给缓存策略，累积指标。"""

    def __init__(self, cache_size: int, trace: Iterable[int]):
        self.cache_size = cache_size
        self.trace: List[int] = list(trace)

    def run(self, algorithm_name: str, cache: Cache) -> SimulationResult:
        """在指定的缓存实例上运行完整跟踪序列并返回统计信息。"""
        hits = 0
        misses = 0
        elapsed = 0

        for page_id in self.trace:
            start = time.perf_counter_ns()
            hit = cache.access(page_id)
            elapsed += time.perf_counter_ns() - start

            if hit:
                hits += 1
            else:
                misses += 1

        return SimulationResult(
            algorithm=algorithm_name,
            cache_size=self.cache_size,
            total_requests=len(self.trace),
            hits=hits,
            misses=misses,
            elapsed_ns=elapsed,
            cache_stats=cache.get_stats(),
        )


