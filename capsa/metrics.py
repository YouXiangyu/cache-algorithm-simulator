from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from .simulator import SimulationResult


CACHE_ACCESS_COST = 1
MEMORY_ACCESS_COST = 10


@dataclass
class ReportConfig:
    cache_size: int
    workload_name: str
    workload_params: dict
    total_requests: int


class MetricsCollector:
    """将原始指标转换为人类可读的报告。"""

    def __init__(self, config: ReportConfig):
        self.config = config

    def _format_result(self, result: SimulationResult) -> str:
        total_simulated_time = (
            result.hits * CACHE_ACCESS_COST + result.misses * MEMORY_ACCESS_COST
        )
        lines = [
            "------------------------------------------------------------",
            f"[Algorithm: {result.algorithm}]",
            "- Performance:",
            f"- Hit Rate: {result.hit_rate:.2f}%",
            f"- Total Simulated Time: {total_simulated_time} units",
            "- Overhead:",
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
            "=" * 60,
            "CAPSA: Simulation Performance Report",
            "=" * 60,
            "",
            "[Simulation Configuration]",
            f"- Cache Size: {self.config.cache_size} pages",
            f"- Workload: {self.config.workload_name}",
            f"- Total Requests: {self.config.total_requests}",
            f"- Parameters: {self.config.workload_params}",
            "",
        ]

        body = "\n\n".join(self._format_result(r) for r in result_list)
        summary = [
            "",
            "=" * 60,
            "[Summary]",
            "Analysis complete. See algorithm sections and ranking tables above.",
            self._build_rankings(result_list),
            "=" * 60,
        ]
        return "\n".join(header + [body] + summary)

    def _calculate_stats(self, values: List[float]) -> Dict[str, float]:
        """计算统计信息：均值、标准差、最小值、最大值"""
        if not values:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance)
        return {
            "mean": mean,
            "std": std,
            "min": min(values),
            "max": max(values),
        }

    def build_batch_report(
        self, all_results_by_algorithm: Dict[str, List[SimulationResult]], run_count: int
    ) -> str:
        """生成批量测试摘要报告"""
        header = [
            "=" * 60,
            "CAPSA: Batch Simulation Performance Report",
            "=" * 60,
            "",
            "[Simulation Configuration]",
            f"- Cache Size: {self.config.cache_size} pages",
            f"- Workload: {self.config.workload_name}",
            f"- Total Requests per Run: {self.config.total_requests}",
            f"- Parameters: {self.config.workload_params}",
            f"- Number of Runs: {run_count}",
            "",
        ]

        # Calculate statistics for each algorithm
        aggregated_results = []
        for algo_name, results in all_results_by_algorithm.items():
            hit_rates = [r.hit_rate for r in results]
            overheads = [r.avg_overhead_ns for r in results]
            total_times = [
                r.hits * CACHE_ACCESS_COST + r.misses * MEMORY_ACCESS_COST for r in results
            ]

            hit_stats = self._calculate_stats(hit_rates)
            overhead_stats = self._calculate_stats(overheads)
            time_stats = self._calculate_stats(total_times)

            aggregated_results.append(
                {
                    "algorithm": algo_name,
                    "hit_rate": hit_stats,
                    "overhead": overhead_stats,
                    "total_time": time_stats,
                }
            )

        # Generate detailed report
        body_lines = []
        for agg in aggregated_results:
            body_lines.append("------------------------------------------------------------")
            body_lines.append(f"[Algorithm: {agg['algorithm']}]")
            body_lines.append(f"- Performance (Average over {run_count} runs):")
            body_lines.append(
                f"  - Hit Rate: {agg['hit_rate']['mean']:.2f}% "
                f"(std: {agg['hit_rate']['std']:.2f}%, "
                f"range: {agg['hit_rate']['min']:.2f}% - {agg['hit_rate']['max']:.2f}%)"
            )
            body_lines.append(
                f"  - Total Simulated Time: {agg['total_time']['mean']:.0f} units "
                f"(std: {agg['total_time']['std']:.0f}, "
                f"range: {agg['total_time']['min']:.0f} - {agg['total_time']['max']:.0f})"
            )
            body_lines.append("- Overhead (Average):")
            body_lines.append(
                f"  - Avg. Time per Request: {agg['overhead']['mean']:.2f} ns "
                f"(std: {agg['overhead']['std']:.2f} ns, "
                f"range: {agg['overhead']['min']:.2f} - {agg['overhead']['max']:.2f} ns)"
            )
            body_lines.append("")

        # Generate ranking tables (based on mean values)
        hit_rank = sorted(aggregated_results, key=lambda x: x["hit_rate"]["mean"], reverse=True)
        hit_rows = [
            (
                str(idx + 1),
                agg["algorithm"],
                f"{agg['hit_rate']['mean']:.2f}%",
                f"±{agg['hit_rate']['std']:.2f}%",
            )
            for idx, agg in enumerate(hit_rank)
        ]

        time_rank = sorted(aggregated_results, key=lambda x: x["overhead"]["mean"])
        time_rows = [
            (
                str(idx + 1),
                agg["algorithm"],
                f"{agg['overhead']['mean']:.2f} ns",
                f"±{agg['overhead']['std']:.2f} ns",
            )
            for idx, agg in enumerate(time_rank)
        ]

        summary = [
            "",
            "=" * 60,
            "[Summary - Average Performance]",
            f"Based on average over {run_count} runs:",
            "",
            "[Hit-Rate Ranking (Mean ± Std)]",
            self._build_table(("Rank", "Algorithm", "Hit Rate", "Std Dev"), hit_rows),
            "",
            "[Runtime Ranking (Mean ± Std)]",
            self._build_table(("Rank", "Algorithm", "Avg Time / Req", "Std Dev"), time_rows),
            "",
            "=" * 60,
        ]

        return "\n".join(header + body_lines + summary)


