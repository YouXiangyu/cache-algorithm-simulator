from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from capsa.trace_suite import TRACE_RECIPES, TraceRecipe, generate_trace


def write_trace(path: Path, seq: Iterable[int]) -> None:
    """将跟踪序列写入文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(str(x) for x in seq))


def main() -> None:
    """生成所有负载的跟踪文件。"""
    out_dir = Path(os.getcwd()) / "traces"
    out_dir.mkdir(parents=True, exist_ok=True)
    for recipe in TRACE_RECIPES:
        seq = generate_trace(recipe.key)
        write_trace(out_dir / recipe.filename, seq)
        print(f"[OK] wrote {recipe.filename} ({len(seq)} entries)")


if __name__ == "__main__":
    main()