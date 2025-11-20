from __future__ import annotations

import os


def wrap_range(start: int, length: int, max_page: int) -> list[int]:
    return [((start - 1 + i) % max_page) + 1 for i in range(length)]


def wl01() -> list[int]:
    total_pages = 1000
    blocks = 500
    trace: list[int] = []
    for _ in range(blocks):
        trace.extend([p for _ in range(8) for p in range(1, 11)])
        trace.extend([11 + (30 * k % 990) for k in range(20)])
    return trace


def wl02() -> list[int]:
    total_pages = 2000
    blocks = 500
    trace: list[int] = []
    for _ in range(blocks):
        trace.extend([p for _ in range(3) for p in range(1, 21)])
        trace.extend([21 + (50 * k % 1980) for k in range(40)])
    return trace


def wl03() -> list[int]:
    total_pages = 500
    blocks = 500
    trace: list[int] = []
    for _ in range(blocks):
        trace.extend([1, 2] * 45)
        trace.extend([3 + (7 * k % 497) for k in range(10)])
    return trace


def wl04() -> list[int]:
    max_page = 1000
    windows = 500
    window_size = 100
    trace: list[int] = []
    for s in range(1, windows + 1):
        trace.extend(wrap_range(s, window_size, max_page))
    return trace


def wl05() -> list[int]:
    max_page = 1200
    windows = 250
    window_size = 200
    trace: list[int] = []
    for s in range(1, windows + 1):
        trace.extend(wrap_range(s, window_size, max_page))
    return trace


def wl06() -> list[int]:
    max_page = 1000
    windows = 500
    window_size = 100
    step = 5
    trace: list[int] = []
    for i in range(windows):
        s = 1 + step * i
        trace.extend(wrap_range(s, window_size, max_page))
    return trace


def wl07() -> list[int]:
    trace: list[int] = []
    hot = list(range(1, 21))
    for _ in range(50):
        trace.extend(hot)
    trace.extend(range(1, 48001))
    for _ in range(50):
        trace.extend(hot)
    return trace


def wl08() -> list[int]:
    trace: list[int] = []
    hot = list(range(1, 21))
    trace.extend(range(1, 20001))
    for _ in range(50):
        trace.extend(hot)
    trace.extend(range(20001, 39501))
    for _ in range(50):
        trace.extend(hot)
    for _ in range(425):
        trace.extend(hot)
    return trace


def wl09() -> list[int]:
    trace: list[int] = []
    for _ in range(250):
        trace.extend([p for _ in range(8) for p in range(1, 11)])
        trace.extend([11 + (30 * k % 990) for k in range(20)])
    max_page = 1000
    window_size = 100
    for s in range(1, 251):
        trace.extend(wrap_range(s, window_size, max_page))
    return trace


def write_trace(path: str, seq: list[int]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(str(x) for x in seq))


def main() -> None:
    out_dir = os.path.join(os.getcwd(), "traces")
    os.makedirs(out_dir, exist_ok=True)
    cases = {
        "WL01_HOT10_80_20.trace": wl01(),
        "WL02_HOT20_60_40.trace": wl02(),
        "WL03_EHOT2_90_10.trace": wl03(),
        "WL04_SW100.trace": wl04(),
        "WL05_SW200.trace": wl05(),
        "WL06_SW100_STEP5.trace": wl06(),
        "WL07_HOT20_SCAN48000.trace": wl07(),
        "WL08_SCAN_SANDWICH.trace": wl08(),
        "WL09_AB_HOT_SW100.trace": wl09(),
    }
    for name, seq in cases.items():
        write_trace(os.path.join(out_dir, name), seq)


if __name__ == "__main__":
    main()