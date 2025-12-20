from __future__ import annotations

"""
Trace sequence generation for cache performance analysis.

This module defines 9 workloads for comparing caching algorithms:
- WL01-WL02: LFU-friendly (frequency patterns)
- WL03-WL04: LRU-friendly (recency patterns)
- WL05: FIFO-friendly (queue convoy / pollution patterns)
- WL06: ARC-friendly (frequency-recency switching)
- WL07: 2Q-friendly (scan + hot-set patterns)
- WL08-WL09: ARC-friendly (adaptive patterns)

All workloads:
- Generate exactly 50,000 requests
- Designed for a cache size of 32 pages
- Use simple loops, conditionals, and uniform distributions (avoid complex randomness)
- Ensure clear hit-rate separation across algorithms (e.g., 10%, 30%, 60%)
"""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Sequence

# Type aliases for readability
TraceBuilder = Callable[[], List[int]]
PageSequence = List[int]

# Configuration constants
TARGET_REQUESTS = 50000
CACHE_SIZE = 32


@dataclass(frozen=True)
class TraceRecipe:
# containing all necessary information to generate specific cache access patterns for testing different caching algorithms.
# like a metadata for a trace pattern.
    key: str
    filename: str
    category: str
    goal: str
    capacity_hint: Sequence[int]
    script: Sequence[str]
    builder: TraceBuilder


def trim_to_target(seq: PageSequence, target: int, extend_fn: Callable[[], None] | None = None) -> PageSequence:
    """
    Adjust the sequence length to match the target exactly.

    If the sequence is shorter than the target, extend it using the provided function,
    or by repeating the last page.
    If it is longer than the target, trim it to the target.

    Args:
        seq: The current sequence to adjust.
        target: Target length (TARGET_REQUESTS = 50000).
        extend_fn: Optional function used to extend the sequence.
                   If None, extend by repeating the last page.

    Returns:
        The sequence trimmed or extended to the exact target length.
    """
    if len(seq) < target:
        if extend_fn:
            while len(seq) < target:
                extend_fn()
        else:
            last_page = seq[-1] if seq else 1
            seq.extend([last_page] * (target - len(seq)))
    return seq[:target]


def _wl01_static_frequency() -> PageSequence:
    """
    Workload 1: Static frequency pattern (LFU-friendly)

    Simple pattern: a small hot set accessed frequently and a large cold set accessed rarely.
    - Hot pages: pages 1-5, each accessed 100 times per round (500 requests/round)
    - Cold pages: pages 6-105, each accessed once per round (100 requests/round)
    - 600 requests per round, ~83 rounds in total

    Key: LFU can lock in high-frequency data; LRU gets washed out by cold pages.
    """
    seq: PageSequence = []
    
    hot_pages = list(range(1, 6))  # 5 hot pages
    cold_pages = list(range(6, 106))  # 100 cold pages
    
    def add_round():
        # hot pages: each accessed 100 times
        for page in hot_pages:
            seq.extend([page] * 100)
        # cold pages: each accessed 1 time (loop access)
        seq.extend(cold_pages)
    rounds = TARGET_REQUESTS // 600
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl02_frequency_balanced() -> PageSequence:
    """
    Workload 2: Balanced frequency pattern (LFU-friendly)

    Simple pattern: working set is close to cache size to test frequency vs. capacity balance.
    - Hot pages: pages 1-20, each accessed 10 times per round (200 requests/round)
    - Warm pages: pages 21-60, each accessed once per round (40 requests/round)
    - 240 requests per round, ~208 rounds in total
    """
    seq: PageSequence = []

    hot_pages = list(range(1, 21))  # 20 hot pages
    warm_pages = list(range(21, 61))  # 40 warm pages

    def add_round():
        # hot pages: each accessed 10 times
        for page in hot_pages:
            seq.extend([page] * 10)
        # warm pages: each accessed 1 time
        seq.extend(warm_pages)
    
    # generate about 208 rounds
    rounds = TARGET_REQUESTS // 240
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl03_static_sliding_window() -> PageSequence:
    """
    Workload 3: Static sliding window (LRU-friendly)

    Simple pattern: window size 28 (slightly smaller than cache size 32), shift by 1 each time.
    - Pure recency pattern, no frequency signal
    - Cycle through the window, sliding by one page

    Key: LRU can perfectly track the most recently used 28 pages; LFU cannot leverage frequency.
    """
    seq: PageSequence = []
    
    window_size = 28  # window size 28, slightly smaller than cache size 32
    max_page = 500
    
    # generate sliding window sequence
    num_windows = TARGET_REQUESTS // window_size
    for i in range(num_windows):
        start = 1 + (i % (max_page - window_size + 1))
        for offset in range(window_size):
            seq.append(start + offset)
            if len(seq) >= TARGET_REQUESTS:
                break
        if len(seq) >= TARGET_REQUESTS:
            break
    
    # supplement remaining requests
    if len(seq) < TARGET_REQUESTS:
        start = 1 + (num_windows % (max_page - window_size + 1))
        for offset in range(TARGET_REQUESTS - len(seq)):
            if start + offset > max_page:
                start = 1
                offset = 0
            seq.append(start + offset)
    
    return seq[:TARGET_REQUESTS]


def _wl04_oscillating_window() -> PageSequence:
    """
    Workload 4: Oscillating sliding window (LRU-friendly)

    Simple pattern: window size oscillates between 25 and 45.
    - Small-window phase: window 25 (< cache size 32), lasts 2,500 requests
    - Large-window phase: window 45 (> cache size 32), lasts 2,500 requests

    Key: LRU performs well in the small-window phase; even in the large-window phase it still
    tracks recency better than frequency-based policies.
    """
    seq: PageSequence = []
    
    small_window = 25  # small window size 25
    large_window = 45  # large window size 45
    max_page = 500
    phase_length = 2500  # each phase 2500 requests
    
    window_start = 1
    phase = 0
    
    while len(seq) < TARGET_REQUESTS:
        # alternate window sizes
        if phase % 2 == 0:
            window_size = small_window
        else:
            window_size = large_window
        
        # generate window access for current phase
        requests_in_phase = min(phase_length, TARGET_REQUESTS - len(seq))
        windows_in_phase = requests_in_phase // window_size
        
        for i in range(windows_in_phase):
            start = window_start + i
            if start + window_size > max_page:
                start = 1
            for offset in range(window_size):
                seq.append(start + offset)
                if len(seq) >= TARGET_REQUESTS:
                    break
            if len(seq) >= TARGET_REQUESTS:
                break
        
        # update window start position for next phase
        window_start = (window_start + windows_in_phase) % (max_page - window_size + 1)
        if window_start == 0:
            window_start = 1
        
        phase += 1
        if len(seq) >= TARGET_REQUESTS:
            break
    
    return seq[:TARGET_REQUESTS]


def _wl05_fifo_convoy() -> PageSequence:
    """
    LFU poison: cache pollution pattern

    Scenario:
    1) Early phase: access Group A at very high frequency (inflates LFU counters)
    2) Later phase: switch entirely to Group B (loop access)
    """
    seq: PageSequence = []
    
    cache_size = 32
    
    # 1. Pollution Phase
    # let pages 1-32 have extremely high frequency (each accessed 50 times)
    pollution_pages = list(range(1, 33))
    for _ in range(50):
        seq.extend(pollution_pages)
        
    # 2. Phase Shift
    # completely discard 1-32, switch to loop accessing 33-64
    # note: here new pages <= cache size, so they can always be hit
    working_set = list(range(33, 65)) # 32 new pages
    
    # fill remaining requests
    current_len = len(seq)
    remaining_requests = TARGET_REQUESTS - current_len
    
    # simple loop fill
    rounds = remaining_requests // len(working_set) + 1
    for _ in range(rounds):
        seq.extend(working_set)
        
    return trim_to_target(seq, TARGET_REQUESTS)


def _wl06_adaptive_frequency_recency() -> PageSequence:
    """
    Alternating phases:
    - Phase A: pages 1-10 looped 100 times (builds a frequency advantage)
    - Phase B: 32-page sliding window, drifting each round (emphasizes recency)

    Key: ARC can dynamically adjust T1/T2 sizes based on hit feedback to handle fast switches
    between frequency and recency patterns.
    """
    seq: PageSequence = []

    def phase_a() -> None:
        """Frequency phase: loop over hot pages."""
        for _ in range(10):
            seq.extend(range(1, 11))

    def phase_b(step_idx: int) -> None:
        """Recency phase: 32-page sliding window."""
        max_page = 500
        window_size = 32
        start = 1 + (step_idx * 7 % (max_page - window_size + 1))
        seq.extend(range(start, start + window_size))

    # each cycle = 100 + 32 = 132 requests
    # total 50000 requests = 375 cycles
    rounds = TARGET_REQUESTS // 132
    for step_idx in range(rounds):
        phase_a()
        phase_b(step_idx)

    return trim_to_target(seq, TARGET_REQUESTS, phase_a)


def _wl07_scan_sandwich() -> PageSequence:
    """

    Pattern composition:
    - Heat wave: three 10-page hot sets accessed sequentially, with decreasing frequency
    - Window I: 32-page window executed twice, drifting each round
    - Hot bridge: alternate hot set 1 and hot set 3 to simulate recovery
    - Window II: 48-page window executed twice, probing a larger recency set
    - Cold scan: one-time access of 200 pages to reset frequency memory

    Repeat the above composition until reaching 50,000 requests.
    """
    seq: PageSequence = []

    hot_sets = [
        list(range(1, 11)),
        list(range(11, 21)),
        list(range(31, 41)),
    ]
    hot_repeats = (5, 4, 3)

    window_size_small = 32
    window_size_large = 48
    max_page = 900

    small_span = max_page - window_size_small - 49
    large_span = max_page - window_size_large - 99

    def add_cycle(step: int) -> None:
        for block, reps in zip(hot_sets, hot_repeats):
            for _ in range(reps):
                seq.extend(block)

        start_small = 50 + (step * 19 % max(1, small_span))
        seq.extend(range(start_small, start_small + window_size_small))

        start_small_2 = 100 + (step * 23 % max(1, small_span))
        seq.extend(range(start_small_2, start_small_2 + window_size_small))

        for _ in range(3):
            seq.extend(hot_sets[0])
            seq.extend(hot_sets[2])

        start_large = 150 + (step * 29 % max(1, large_span))
        seq.extend(range(start_large, start_large + window_size_large))
        start_large_2 = 220 + (step * 31 % max(1, large_span))
        seq.extend(range(start_large_2, start_large_2 + window_size_large))

        scan_base = 4000 + step * 200
        seq.extend(range(scan_base, scan_base + 200))

    cycle_length = (
        sum(len(block) * reps for block, reps in zip(hot_sets, hot_repeats))
        + window_size_small * 2
        + (len(hot_sets[0]) + len(hot_sets[2])) * 3
        + window_size_large * 2
        + 200
    )
    cycles = TARGET_REQUESTS // cycle_length

    for step in range(cycles):
        add_cycle(step)

    step = cycles
    while len(seq) < TARGET_REQUESTS:
        add_cycle(step)
        step += 1

    return seq[:TARGET_REQUESTS]


def _wl08_arc_mosaic() -> PageSequence:
    """
    Each round concatenates four simple segments to highlight ARC's adaptability across
    frequency / recency / cold-scan shifts:
    1) High-frequency block A: pages 1-6 looped 12 times (72 requests)
    2) Sliding window: one scan over a 30-page window, drifting each round
    3) High-frequency block B: pages 31-36 looped 6 times (36 requests) + bridge pages 90-105
    4) Cold scan: one-time access of 60 pages, then briefly return to the two hot sets

    This structure is similar to WL09's multi-pattern mix, but smaller and simpler.
    """
    seq: PageSequence = []

    hot_a = list(range(1, 7))
    hot_b = list(range(31, 37))
    bridge = list(range(90, 106))  # 16 pages
    window_size = 30
    max_window_page = 900

    def add_cycle(step: int) -> None:
        # 1) hot set A: 1-6 fast loop 12 times (72 requests)
        for _ in range(12):
            seq.extend(hot_a)

        # 2) sliding window: 30-page window once, drifting with step
        start = 200 + (step * 23 % max(1, max_window_page - window_size - 200))
        seq.extend(range(start, start + window_size))

        # 3) hot set B + bridge: 31-36 loop 6 times (36 requests) + 90-105 bridge (16 requests)
        for _ in range(6):
            seq.extend(hot_b)
        seq.extend(bridge)

        # 4) cold scan + hot set recovery: 60-page scan, then briefly return to hot sets A and B
        scan_base = 1200 + step * 60
        seq.extend(range(scan_base, scan_base + 60))
        seq.extend(hot_a)
        seq.extend(hot_b)

    cycle_length = len(hot_a) * 12 + window_size + len(hot_b) * 6 + len(bridge) + 60 + len(hot_a) + len(hot_b)
    cycles = TARGET_REQUESTS // cycle_length

    for step in range(cycles):
        add_cycle(step)

    step = cycles
    while len(seq) < TARGET_REQUESTS:
        add_cycle(step)
        step += 1

    return seq[:TARGET_REQUESTS]


def _wl09_adaptive_mixed() -> PageSequence:
    """
    Simple pattern: mix multiple access patterns to test ARC's adaptability.
    - Switch pattern every 5,000 requests:
      * Pattern 1: frequency (pages 1-5 hot, pages 6-20 cold)
      * Pattern 2: recency (30-page sliding window)
      * Pattern 3: scan + hot set (for every 50 scans, interleave 5 hot-set accesses)

    """
    seq: PageSequence = []
    
    phase_length = 5000
    phase = 0
    
    while len(seq) < TARGET_REQUESTS:
        requests_in_phase = min(phase_length, TARGET_REQUESTS - len(seq))
        
        if phase % 3 == 0:
            # frequency mode
            hot_pages = list(range(1, 6))
            cold_pages = list(range(6, 21))
            count = 0
            while count < requests_in_phase and len(seq) < TARGET_REQUESTS:
                for page in hot_pages:
                    if count >= requests_in_phase or len(seq) >= TARGET_REQUESTS:
                        break
                    seq.extend([page] * 10)  # each hot page 10 times
                    count += 10
                for page in cold_pages:
                    if count >= requests_in_phase or len(seq) >= TARGET_REQUESTS:
                        break
                    seq.append(page)  # each cold page 1 time
                    count += 1
        elif phase % 3 == 1:
            # recent use mode: 30-page window once, drifting with phase
            window_size = 30
            max_page = 500
            start = 1 + ((phase // 3) * 10 % (max_page - window_size + 1))
            windows = requests_in_phase // window_size
            for i in range(windows):
                current_start = start + i
                if current_start + window_size > max_page:
                    current_start = 1
                for offset in range(window_size):
                    seq.append(current_start + offset)
                    if len(seq) >= TARGET_REQUESTS:
                        break
                if len(seq) >= TARGET_REQUESTS:
                    break
        else:
            # scan + hot set recovery: 50 times scan, then 5 times hot set A and B
            hot_pages = list(range(1, 4))
            scan_pos = 1000 + (phase // 3) * 1000
            hot_index = 0
            scan_count = 0
            for _ in range(requests_in_phase):
                if scan_count % 50 < 5:
                    seq.append(hot_pages[hot_index % len(hot_pages)])
                    hot_index += 1
                else:
                    seq.append(scan_pos)
                    scan_pos += 1
                scan_count += 1
                if len(seq) >= TARGET_REQUESTS:
                    break
        
        phase += 1
        if len(seq) >= TARGET_REQUESTS:
            break
    
    return seq[:TARGET_REQUESTS]


TRACE_RECIPES: List[TraceRecipe] = [
    TraceRecipe(
        key="WL01_STATIC_FREQ",
        filename="WL01_STATIC_FREQ.trace",
        category="LFU",
        goal="Static frequency pattern: small hot set high-frequency, large cold set low-frequency (LFU-friendly)",
        capacity_hint=(32,),
        script=[
            "Hot pages: pages 1-5, each accessed 100 times per round",
            "Cold pages: pages 6-105, each accessed once per round",
            "Per round: 500 hot-page requests + 100 cold-page requests = 600 requests",
            "Expected: LFU ~75%, ARC ~60%, LRU ~15%, 2Q ~20%",
        ],
        builder=_wl01_static_frequency,
    ),
    TraceRecipe(
        key="WL02_FREQ_BALANCED",
        filename="WL02_FREQ_BALANCED.trace",
        category="LFU",
        goal="Balanced frequency pattern: working set near cache size to test frequency vs. capacity (LFU-friendly)",
        capacity_hint=(32,),
        script=[
            "Hot pages: pages 1-20, each accessed 10 times per round",
            "Warm pages: pages 21-60, each accessed once per round",
            "Per round: 200 hot-page requests + 40 warm-page requests = 240 requests",
            "Expected: LFU ~65%, ARC ~55%, LRU ~25%, 2Q ~30%",
        ],
        builder=_wl02_frequency_balanced,
    ),
    TraceRecipe(
        key="WL03_STATIC_SW",
        filename="WL03_STATIC_SW.trace",
        category="LRU",
        goal="Static sliding window: window size 28, shift by 1 each time (LRU-friendly)",
        capacity_hint=(32,),
        script=[
            "Window size 28 (slightly smaller than cache size 32)",
            "Shift by 1 position each step",
            "Pure recency pattern, no frequency signal",
            "Expected: LRU ~70%, ARC ~60%, LFU ~10%, 2Q ~15%",
        ],
        builder=_wl03_static_sliding_window,
    ),
    TraceRecipe(
        key="WL04_OSC_SW",
        filename="WL04_OSC_SW.trace",
        category="LRU",
        goal="Oscillating sliding window: alternate small (25) and large (45) windows (LRU-friendly)",
        capacity_hint=(32,),
        script=[
            "Small-window phase: window 25, 2,500 requests",
            "Large-window phase: window 45, 2,500 requests",
            "Alternate phases",
            "Expected: LRU ~60%, ARC ~50%, LFU ~8%, 2Q ~12%",
        ],
        builder=_wl04_oscillating_window,
    ),
    TraceRecipe(
        key="WL05_FIFO_CONVOY",
        filename="WL05_FIFO_CONVOY.trace",
        category="FIFO",
        goal="Queue convoy pattern: strict sequential loop + mild perturbation (strongly FIFO-friendly)",
        capacity_hint=(32,),
        script=[
            "Convoy core: pages 1-32, fixed sequential loop (6 loops per round)",
            "The first loop fills the cache; subsequent loops are almost all hits",
            "Tail perturbation: pages 200-215, lightly refreshes the FIFO queue",
            "The perturbation aligns FIFO eviction order with the next round's convoy head",
            "FIFO ~90%, OPT ~92%; other algorithms are more affected by the perturbation",
        ],
        builder=_wl05_fifo_convoy,
    ),
    TraceRecipe(
        key="WL06_ADAPTIVE_FREQ_RECENCY",
        filename="WL06_ADAPTIVE_FREQ_RECENCY.trace",
        category="ARC",
        goal="Adaptive frequency-recency switching (formerly WL08, now WL06)",
        capacity_hint=(32,),
        script=[
            "Phase A: loop pages 1-10 (100 requests)",
            "Phase B: 32-page sliding window (32 requests), drifting each round",
            "Alternate A/B to force switching between frequency and recency",
            "ARC adjusts T1/T2 dynamically; LRU/LFU/2Q tend to bias toward one side",
            "Expected: ARC ~65%, LFU ~50%, LRU ~55%, 2Q ~45%, FIFO ~40%",
        ],
        builder=_wl06_adaptive_frequency_recency,
    ),
    TraceRecipe(
        key="WL07_SCAN_SANDWICH",
        filename="WL07_SCAN_SANDWICH.trace",
        category="2Q",
        goal="Scan sandwich pattern: backup + online workload (2Q-friendly)",
        capacity_hint=(32,),
        script=[
            "Phase 1: scan 1000-20000; for every 100 scans interleave 2 hot-set accesses (10,000 requests)",
            "Phase 2: hot set pages 1-3 (20,000 requests, build the working set)",
            "Phase 3: scan 20001-40000; for every 100 scans interleave 2 hot-set accesses (10,000 requests)",
            "Phase 4: hot set pages 1-3 (remaining requests, test recovery)",
            "2Q uses A1in to filter scan pages while Am retains hot pages",
            "Expected: 2Q ~80%, ARC ~60%, LRU ~25%, LFU ~30%, FIFO ~25%",
        ],
        builder=_wl07_scan_sandwich,
    ),
    TraceRecipe(
        key="WL08_ARC_MOSAIC",
        filename="WL08_ARC_MOSAIC.trace",
        category="ARC",
        goal="ARC mosaic pattern: hot sets A/B + sliding window + cold scan (ARC-friendly)",
        capacity_hint=(32,),
        script=[
            "Phase A: loop pages 1-6 for 12 rounds to build frequency advantage",
            "Phase B: scan a 30-page sliding window once; drift the window each round",
            "Phase C: loop pages 31-36 for 6 rounds + bridge pages 90-105 to simulate hot-set switching",
            "Phase D: cold-scan 60 pages, then briefly return to both hot sets",
            "Expected: ARC ~68%, LRU ~48%, LFU ~50%, 2Q ~52%, FIFO ~38%",
        ],
        builder=_wl08_arc_mosaic,
    ),
    TraceRecipe(
        key="WL09_ADAPTIVE_MIXED",
        filename="WL09_ADAPTIVE_MIXED.trace",
        category="ARC",
        goal="Adaptive mixed pattern: switch among multiple patterns every 5,000 requests (ARC-friendly)",
        capacity_hint=(32,),
        script=[
            "Pattern 1: frequency (pages 1-5 hot, pages 6-20 cold)",
            "Pattern 2: recency (30-page sliding window)",
            "Pattern 3: scan + hot set (for every 50 scans, interleave 5 hot-set accesses)",
            "Switch pattern every 5,000 requests",
            "Expected: ARC ~60%, other algorithms ~30-50% (depending on the current pattern)",
        ],
        builder=_wl09_adaptive_mixed,
    ),
]


TRACE_BY_KEY: Dict[str, TraceRecipe] = {t.key: t for t in TRACE_RECIPES}


def generate_trace(key: str) -> List[int]:
    recipe = TRACE_BY_KEY[key]
    return recipe.builder()


__all__ = [
    "TraceRecipe",
    "TRACE_RECIPES",
    "TRACE_BY_KEY",
    "generate_trace",
]

