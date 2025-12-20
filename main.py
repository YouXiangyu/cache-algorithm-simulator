
from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict, List

from capsa.caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache, TwoQCache
from capsa.metrics import MetricsCollector, ReportConfig
from capsa.simulator import Simulator, SimulationResult
from capsa.trace_suite import TRACE_BY_KEY, TRACE_RECIPES, generate_trace

# constant setup
CACHE_SIZE = 32
ALGORITHMS = ["LFU", "LRU", "FIFO", "2Q", "ARC", "OPT"]
NON_OPT_ALGOS = [algo for algo in ALGORITHMS if algo != "OPT"]
TOTAL_WORKLOADS = len(TRACE_RECIPES)

WORKLOAD_COL_WIDTH = 25
VALUE_COL_WIDTH = 12
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_GREEN = "\033[32m"
SUPPORTS_ANSI = sys.stdout.isatty()
TWO_Q_A1OUT_FIXED = 32
TWO_Q_A1IN_MAX = 16


def tune_two_q_offline(cache_size: int, trace: List[int]) -> tuple[int, float]:
    simulator = Simulator(cache_size, trace)
    search_upper = min(TWO_Q_A1IN_MAX, cache_size - 1)
    best_a1in = 1
    best_hit_rate = -1.0
    
    for a1in in range(1, search_upper + 1):
        cache = TwoQCache(cache_size, a1in_size=a1in, a1out_size=TWO_Q_A1OUT_FIXED)
        result = simulator.run("2Q", cache)
        if result.hit_rate > best_hit_rate:
            best_hit_rate = result.hit_rate
            best_a1in = a1in
    
    return best_a1in, best_hit_rate


def emphasize_best_cell(text: str) -> str:
    """
    highlight the best cell in the table
    """
    if not SUPPORTS_ANSI:
        return text
    return f"{ANSI_BOLD}{ANSI_GREEN}{text}{ANSI_RESET}"


def build_cache_factories(
    cache_size: int,
    trace: List[int],
    *,
    two_q_params: Dict[str, object] | None = None,
) -> Dict[str, Callable[[], object]]:
    """
    build cache instance for all algorithms
    """
    return {
        "LRU": lambda: LRUCache(cache_size),
        "LFU": lambda: LFUCache(cache_size),
        "FIFO": lambda: FIFOCache(cache_size),
        "ARC": lambda: ARCCache(cache_size),
        "OPT": lambda: OPTCache(cache_size, trace),
        "2Q": lambda: TwoQCache(cache_size, **(two_q_params or {})),
    }


def run_workload(cache_size: int, recipe_key: str, silent: bool = False) -> List[SimulationResult]:
    """
    run a single workload and return results
    """
    recipe = TRACE_BY_KEY[recipe_key]
    trace = generate_trace(recipe_key)
    best_a1in, best_two_q_hit = tune_two_q_offline(cache_size, trace)
    two_q_params = {"a1in_size": best_a1in, "a1out_size": TWO_Q_A1OUT_FIXED}
    factories = build_cache_factories(cache_size, trace, two_q_params=two_q_params)
    simulator = Simulator(cache_size, trace)
    results = []
    
    for algo_name in ALGORITHMS:
        cache = factories[algo_name]()
        results.append(simulator.run(algo_name, cache))
    
    if not silent:
        params = {
            "recipe": recipe.key,
            "category": recipe.category,
            "steps": list(recipe.script),
            "capacity_hint": list(recipe.capacity_hint),
            "two_q_best_a1in": best_a1in,
            "two_q_best_hit_rate": round(best_two_q_hit, 2),
        }
        report_config = ReportConfig(
            cache_size=cache_size,
            workload_name=recipe.category,
            workload_params=params,
            total_requests=len(trace),
        )
        collector = MetricsCollector(report_config)
        print(collector.build_report(results))
        print(f"[2Q offline tuning] A1in={best_a1in}, A1out={TWO_Q_A1OUT_FIXED}, HitRate={best_two_q_hit:.2f}%")
    
    return results


def extract_better_indicator(goal: str) -> str:
    """   
    Returns:
        if goal contains any better indicator, return the indicator, otherwise return empty string
    """
    indicators = ["(LFU better)", "(LRU better)", "(2Q better)", "(ARC adaptive)"]
    for indicator in indicators:
        if indicator in goal:
            return indicator
    return ""


def format_workload_description(recipe) -> tuple[str, str]:
    indicator = extract_better_indicator(recipe.goal)
    clean_goal = recipe.goal
    for ind in ["(LFU better)", "(LRU better)", "(2Q better)", "(ARC adaptive)"]:
        clean_goal = clean_goal.replace(ind, "")
    clean_goal = clean_goal.strip()
    return indicator, clean_goal


def display_workload_menu() -> None:
    print("\n" + "=" * 60)
    print("Cache Performance Analysis - Workload Selection")
    print("=" * 60)
    print(f"\nCache Size: {CACHE_SIZE} pages")
    print(f"Requests per workload: 50000\n")
    print("Available Workloads:")
    print("-" * 60)
    
    for idx, recipe in enumerate(TRACE_RECIPES, 1):
        indicator, clean_goal = format_workload_description(recipe)
        print(f"{idx}. {recipe.key} {indicator}")
        print(f"   {clean_goal}")
    
    print("-" * 60)
    print(f"\nEnter workload numbers (1-{TOTAL_WORKLOADS}) separated by spaces or commas (e.g., 1 3 5 or 1,3,5):")
    print("Or press Enter to run all workloads:")


def parse_user_selection(user_input: str, num_workloads: int) -> List[int]:
    if not user_input.strip():
        return list(range(1, num_workloads + 1))
    
    selections = []
    for part in user_input.replace(",", " ").split():
        try:
            num = int(part)
            if 1 <= num <= num_workloads:
                selections.append(num)
            else:
                print(f"Warning: {num} is out of range (1-{num_workloads}), ignoring.")
        except ValueError:
            print(f"Warning: '{part}' is not a valid number, ignoring.")
    
    if not selections:
        print("No valid selections. Running all workloads.")
        return list(range(1, num_workloads + 1))
    
    return sorted(set(selections))  # Remove duplicates and sort


def show_interactive_menu() -> List[int]:
    display_workload_menu()
    
    try:
        user_input = input("> ").strip()
        return parse_user_selection(user_input, len(TRACE_RECIPES))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return []


def parse_workload_argument(arg: str) -> tuple[int | None, str | None]:
    # check if arg is -all or --all
    if arg.lower() == "-all" or arg.lower() == "--all":
        return -1, None
    
    # check if arg is a number (negative or positive)
    if arg.startswith("-") and arg[1:].isdigit():
        num = int(arg[1:])  # remove minus sign
        if 1 <= num <= len(TRACE_RECIPES):
            return num, None
        else:
            raise ValueError(f"Workload number {num} is out of range (1-{len(TRACE_RECIPES)})")
    
    # check if arg is a workload key
    if arg in TRACE_BY_KEY:
        return None, arg
    
    raise ValueError(
        f"Unknown workload '{arg}'. Use workload numbers (1-{TOTAL_WORKLOADS}), workload keys, or -all to run all workloads"
    )


def run_all_workloads_summary() -> None:
    print("\n" + "=" * 80)
    print("CAPSA - Running all workloads with summary table")
    print("=" * 80)
    print(f"\nCache size: {CACHE_SIZE} pages")
    print(f"Requests per workload: 50000\n")
    print("Running all workloads, please wait...\n")
    
    all_results: Dict[str, Dict[str, float]] = {}
    
    for idx, recipe in enumerate(TRACE_RECIPES, 1):
        print(f"Running workload {idx}/{TOTAL_WORKLOADS}: {recipe.key}...", end=" ", flush=True)
        results = run_workload(CACHE_SIZE, recipe.key, silent=True)

        workload_results = {}
        for result in results:
            workload_results[result.algorithm] = result.hit_rate
        all_results[recipe.key] = workload_results
        print("Done")
    

    print("\n" + "=" * 80)
    print("Hit rate summary (%)")
    print("=" * 80 + "\n")

    header_cells = [f"{'Workload':<{WORKLOAD_COL_WIDTH}}"]
    header_cells.extend(f"{algo:>{VALUE_COL_WIDTH}}" for algo in ALGORITHMS)
    header = " ".join(header_cells)
    table_width = len(header.replace(ANSI_BOLD, "").replace(ANSI_GREEN, "").replace(ANSI_RESET, ""))
    print(header)
    print("-" * table_width)
    
    # display
    for workload_name in sorted(all_results.keys()):
        workload_results = all_results[workload_name]
        best_hit_rate = (
            max((workload_results.get(algo, 0.0) for algo in NON_OPT_ALGOS), default=0.0)
            if workload_results
            else 0.0
        )
        row_cells = [f"{workload_name:<{WORKLOAD_COL_WIDTH}}"]
        for algo in ALGORITHMS:
            hit_rate = workload_results.get(algo, 0.0)
            cell = f"{hit_rate:>{VALUE_COL_WIDTH}.2f}"
            if algo != "OPT" and abs(hit_rate - best_hit_rate) < 1e-9:
                cell = emphasize_best_cell(cell)
            row_cells.append(cell)
        print(" ".join(row_cells))
    
    print("\n" + "=" * 80)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CAPSA - Cache Algorithm Performance Simulator & Analyzer",
        epilog="Examples:\n  python main.py -1          # Run workload 1\n  python main.py -1 -3 -5    # Run workloads 1, 3, 5\n  python main.py -all         # Run all workloads with summary table\n  python main.py             # Interactive menu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "workloads",
        nargs="*",
        help=f"Workload numbers (1-{TOTAL_WORKLOADS}) or workload keys. Use -1 for workload 1, etc.",
    )
    return parser.parse_args(argv)


def main() -> None:
    f"""
    Mode 1: Interactive Menu (Recommended)
    python main.py

    Mode 2: Command Line Arguments
    python main.py -1          # Run workload 1
    python main.py -1 -3 -5    # Run workloads 1, 3, and 5
    python main.py -{TOTAL_WORKLOADS}          # Run workload {TOTAL_WORKLOADS}

    Mode 3: Run all workloads and show summary table (Recommended for quick comparison)
    python main.py -all        # Run all workloads and display a beautiful hit rate summary table
    """
    # check if -all parameter is provided
    if len(sys.argv) > 1 and (sys.argv[1].lower() == "-all" or sys.argv[1].lower() == "--all"):
        run_all_workloads_summary()
        return
    
    args = parse_arguments(sys.argv[1:])
    
    selected_indices: List[int] = []
    workload_keys: List[str] = []
    
    for arg in args.workloads:
        try:
            idx, key = parse_workload_argument(arg)
            if idx is not None:
                selected_indices.append(idx)
            elif key is not None:
                workload_keys.append(key)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    # if no workloads are selected, show interactive menu
    if not selected_indices and not workload_keys:
        selected_indices = show_interactive_menu()
        if not selected_indices:
            return
    
    # run selected workloads
    for idx in selected_indices:
        recipe = TRACE_RECIPES[idx - 1]  
        print(f"\n{'=' * 60}")
        print(f"Running Workload {idx}: {recipe.key}")
        print(f"{'=' * 60}\n")
        run_workload(CACHE_SIZE, recipe.key)
    
    for key in workload_keys:
        print(f"\n{'=' * 60}")
        print(f"Running Workload: {key}")
        print(f"{'=' * 60}\n")
        run_workload(CACHE_SIZE, key)


if __name__ == "__main__":
    main()
