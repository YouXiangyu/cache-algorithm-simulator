from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Set

from ..cache_base import Cache


class FIFOCache(Cache):

    def __init__(self, size: int):
        super().__init__(size)
        self.queue: Deque[int] = deque()
        self.members: Set[int] = set()
        self.hits = 0
        self.misses = 0

    def access(self, page_id: int) -> bool:
        if page_id in self.members:
            self.hits += 1
            return True

        self.misses += 1
        if len(self.queue) >= self.size:
            evicted = self.queue.popleft()
            self.members.remove(evicted)

        self.queue.append(page_id)
        self.members.add(page_id)
        return False

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}


