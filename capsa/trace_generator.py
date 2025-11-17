from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class WorkloadType(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    OSCILLATING = "oscillating"


@dataclass
class TraceProfile:
    workload: WorkloadType
    parameters: Dict[str, int | float]


@dataclass
class TraceGenerator:
    workload: WorkloadType
    parameters: Dict[str, int | float]
    seed: Optional[int] = None
    profile: TraceProfile = field(init=False)

    def __post_init__(self) -> None:
        if self.seed is not None:
            random.seed(self.seed)
        self.profile = TraceProfile(self.workload, dict(self.parameters))

    def generate(self) -> List[int]:
        if self.workload is WorkloadType.STATIC:
            return self._generate_static()
        if self.workload is WorkloadType.DYNAMIC:
            return self._generate_dynamic()
        if self.workload is WorkloadType.OSCILLATING:
            return self._generate_oscillating()
        raise ValueError(f"未知的工作负载类型: {self.workload}")

    # --- workload implementations -------------------------------------------------
    def _generate_static(self) -> List[int]:
        total_requests = int(self.parameters.get("total_requests", 10000))
        total_pages = max(2, int(self.parameters.get("total_pages", 1000)))
        hot_ratio = float(self.parameters.get("hot_ratio", 0.8))
        scan_ratio = float(self.parameters.get("scan_ratio", 0.2))

        hot_set_size = max(1, int(total_pages * hot_ratio))
        scan_set_size = max(1, int(total_pages * scan_ratio))

        hot_pages = list(range(hot_set_size))
        scan_pages = list(range(hot_set_size, hot_set_size + scan_set_size))
        trace: List[int] = []
        scan_cursor = 0

        for _ in range(total_requests):
            if random.random() < hot_ratio:
                trace.append(random.choice(hot_pages))
            else:
                trace.append(scan_pages[scan_cursor % len(scan_pages)])
                scan_cursor += 1
        return trace

    def _generate_dynamic(self) -> List[int]:
        total_requests = int(self.parameters.get("total_requests", 20000))
        hot_set_size = max(1, int(self.parameters.get("hot_set_size", 100)))
        scan_length = max(1, int(self.parameters.get("scan_length", 500)))
        phases = max(1, int(self.parameters.get("phases", 4)))

        hot_pages = list(range(hot_set_size))
        trace: List[int] = []
        next_scan_page = hot_set_size
        requests_per_phase = total_requests // phases
        hot_accesses = max(0, requests_per_phase - scan_length)

        for phase in range(phases):
            for _ in range(hot_accesses):
                trace.append(random.choice(hot_pages))
            for _ in range(scan_length):
                trace.append(next_scan_page)
                next_scan_page += 1

        while len(trace) < total_requests:
            trace.append(random.choice(hot_pages))

        return trace[:total_requests]

    def _generate_oscillating(self) -> List[int]:
        cycles = max(1, int(self.parameters.get("cycles", 5)))
        hot_burst = max(1, int(self.parameters.get("hot_burst", 2000)))
        scan_burst = max(1, int(self.parameters.get("scan_burst", 2000)))
        hot_set_size = max(1, int(self.parameters.get("hot_set_size", 100)))

        hot_pages = list(range(hot_set_size))
        trace: List[int] = []
        next_scan_page = hot_set_size

        for _ in range(cycles):
            for _ in range(hot_burst):
                trace.append(random.choice(hot_pages))
            for _ in range(scan_burst):
                trace.append(next_scan_page)
                next_scan_page += 1

        total_requests = cycles * (hot_burst + scan_burst)
        self.profile.parameters["total_requests"] = total_requests
        return trace


