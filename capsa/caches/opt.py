from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, DefaultDict, Dict, Iterable, List, Optional, Set

from ..cache_base import Cache


class OPTCache(Cache):
    """具有预知未来能力的理论最优缓存策略。"""

    def __init__(self, size: int, trace: Optional[Iterable[int]] = None):
        super().__init__(size)
        self.trace_preloaded = trace is not None
        self.future_positions: DefaultDict[int, Deque[int]] = defaultdict(deque)
        self.cache: Set[int] = set()
        self.current_step = 0
        self.hits = 0
        self.misses = 0

        if trace is not None:
            self._preprocess_trace(trace)

    def _preprocess_trace(self, trace: Iterable[int]) -> None:
        self.future_positions.clear()
        for index, page_id in enumerate(trace):
            self.future_positions[page_id].append(index)

    def prime(self, trace: Iterable[int]) -> None:
        """当实例初始化时没有 trace，可通过 prime 预加载。"""
        self._preprocess_trace(trace)

    def _drop_current_reference(self, page_id: int) -> None:
        positions = self.future_positions.get(page_id)
        if positions and positions[0] == self.current_step:
            positions.popleft()

    def _select_victim(self) -> int:
        farthest_distance = -1
        victim = None
        for page in self.cache:
            positions = self.future_positions.get(page)
            if not positions:
                return page
            if positions[0] > farthest_distance:
                farthest_distance = positions[0]
                victim = page
        assert victim is not None
        return victim

    def access(self, page_id: int) -> bool:
        self._drop_current_reference(page_id)

        hit = page_id in self.cache
        if hit:
            self.hits += 1
        else:
            self.misses += 1
            if len(self.cache) >= self.size:
                victim = self._select_victim()
                self.cache.remove(victim)
            self.cache.add(page_id)

        self.current_step += 1
        return hit

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}


