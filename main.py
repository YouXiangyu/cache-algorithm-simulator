from __future__ import annotations

import os
import sys
from typing import Callable, Dict, List

from capsa.caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache, TwoQCache
from capsa.metrics import MetricsCollector, ReportConfig
from capsa.simulator import Simulator


def _find_default_traces_dir() -> str | None:
    candidates = [
        os.path.join(os.path.dirname(__file__), "traces"),
        os.path.join(os.getcwd(), "traces"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return None


def _read_trace_file(path: str) -> List[int]:
    seq: List[int] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            token = s.split()[0]
            try:
                seq.append(int(token))
            except ValueError:
                pass
    return seq


def _build_cache_factories(cache_size: int, trace: List[int]) -> Dict[str, Callable[[], object]]:
    return {
        "LRU": lambda: LRUCache(cache_size),
        "LFU": lambda: LFUCache(cache_size),
        "FIFO": lambda: FIFOCache(cache_size),
        "ARC": lambda: ARCCache(cache_size),
        "OPT": lambda: OPTCache(cache_size, trace),
        "2Q": lambda: TwoQCache(cache_size),
    }


def _run_on_trace(cache_size: int, trace: List[int], source_name: str) -> str:
    factories = _build_cache_factories(cache_size, trace)
    simulator = Simulator(cache_size, trace)
    results = []
    for name in ["LRU", "LFU", "FIFO", "ARC", "OPT", "2Q"]:
        cache = factories[name]()
        results.append(simulator.run(name, cache))
    report_config = ReportConfig(
        cache_size=cache_size,
        workload_name="File",
        workload_params={"source": source_name},
        total_requests=len(trace),
    )
    collector = MetricsCollector(report_config)
    return collector.build_report(results)


def main() -> None:
    args = sys.argv[1:]
    cache_size = int(os.environ.get("CAPSA_CACHE_SIZE", "256"))
    if args:
        target = args[0]
        if os.path.isdir(target):
            files = sorted([n for n in os.listdir(target) if n.endswith(".trace")])
            if not files:
                print("No .trace files found in directory")
                return
            for name in files:
                path = os.path.join(target, name)
                trace = _read_trace_file(path)
                print(_run_on_trace(cache_size, trace, name))
        else:
            trace = _read_trace_file(target)
            print(_run_on_trace(cache_size, trace, os.path.basename(target)))
    else:
        base = _find_default_traces_dir()
        if not base:
            print("No traces directory found. Provide a .trace path.")
            return
        files = sorted([n for n in os.listdir(base) if n.endswith(".trace")])
        if not files:
            print("No .trace files found in traces dir.")
            return
        for name in files:
            path = os.path.join(base, name)
            trace = _read_trace_file(path)
            print(_run_on_trace(cache_size, trace, name))


if __name__ == "__main__":
    main()


