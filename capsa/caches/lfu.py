from __future__ import annotations

from collections import defaultdict, OrderedDict
from typing import DefaultDict, Dict

from ..cache_base import Cache


class LFUCache(Cache):

    def __init__(self, size: int):
        super().__init__(size)
        self.key_freq: Dict[int, int] = {}
        self.freq_keys: DefaultDict[int, "OrderedDict[int, None]"] = defaultdict(OrderedDict)
        self.min_freq = 0
        self.hits = 0
        self.misses = 0

    def _bump(self, page_id: int) -> None:
        freq = self.key_freq[page_id]
        self.freq_keys[freq].pop(page_id, None)
        if not self.freq_keys[freq]:
            del self.freq_keys[freq]
            if self.min_freq == freq:
                self.min_freq += 1

        new_freq = freq + 1
        self.key_freq[page_id] = new_freq
        self.freq_keys[new_freq][page_id] = None

    def access(self, page_id: int) -> bool:
        if page_id in self.key_freq:
            self.hits += 1
            self._bump(page_id)
            return True

        self.misses += 1
        if len(self.key_freq) >= self.size:
            lfu_keys = self.freq_keys[self.min_freq]
            victim, _ = lfu_keys.popitem(last=False)
            if not lfu_keys:
                del self.freq_keys[self.min_freq]
            del self.key_freq[victim]

        self.key_freq[page_id] = 1
        self.freq_keys[1][page_id] = None
        self.min_freq = 1
        return False

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}


