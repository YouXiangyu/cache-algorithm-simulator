from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .simulator import SimulationResult


@dataclass
class ReportConfig:
    cache_size: int
    workload_name: str
    workload_params: dict
    total_requests: int


class MetricsCollector:
    """generate report for simulation results"""

    def __init__(self, config: ReportConfig):
        self.config = config

    def _format_result(self, result: SimulationResult) -> str:
        lines = [
            f"[Algorithm: {result.algorithm}]",
            f"- Hit Rate: {result.hit_rate:.2f}%",
            f"- Avg. Time per Request: {result.avg_overhead_ns:.2f} ns",
        ]
        return "\n".join(lines)

    def _build_table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
        if not rows:
            return "(No data)"
        widths = [
            max(len(str(headers[i])), *(len(str(row[i])) for row in rows)) for i in range(len(headers))
        ]

        def _format_row(row: Sequence[str]) -> str:
            return "| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))) + " |"

        header_line = _format_row(headers)
        separator = "|-" + "-|-".join("-" * widths[i] for i in range(len(headers))) + "-|"
        body_lines = [_format_row(row) for row in rows]
        return "\n".join([header_line, separator, *body_lines])

    def _build_rankings(self, results: List[SimulationResult]) -> str:
        if not results:
            return ""
        hit_rank = sorted(results, key=lambda r: r.hit_rate, reverse=True)
        hit_rows = [
            (str(idx + 1), r.algorithm, f"{r.hit_rate:.2f}%") for idx, r in enumerate(hit_rank)
        ]
        time_rank = sorted(results, key=lambda r: r.avg_overhead_ns)
        time_rows = [
            (str(idx + 1), r.algorithm, f"{r.avg_overhead_ns:.2f} ns")
            for idx, r in enumerate(time_rank)
        ]
        return "\n".join(
            [
                "",
                "[Hit-Rate Ranking]",
                self._build_table(("Rank", "Algorithm", "Hit Rate"), hit_rows),
                "",
                "[Runtime Ranking]",
                self._build_table(("Rank", "Algorithm", "Avg Time / Req"), time_rows),
            ]
        )

    def build_report(self, results: Iterable[SimulationResult]) -> str:
        result_list = list(results)
        header = [
            "[Simulation Configuration]",
            f"- Cache Size: {self.config.cache_size} pages",
            f"- Workload: {self.config.workload_name}",
            f"- Total Requests: {self.config.total_requests}",
            "",
        ]

        body = "\n\n".join(self._format_result(r) for r in result_list)
        summary = [
            "",
            "[Summary]",
            "Analysis complete. See algorithm sections and ranking tables above.",
            self._build_rankings(result_list),
        ]
        return "\n".join(header + [body] + summary)


