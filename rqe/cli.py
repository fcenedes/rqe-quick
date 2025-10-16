"""
Beautiful CLI interface for Redis RediSearch benchmarks using Click and Rich.
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.layout import Layout
from rich import box
from rich.text import Text

try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

from .config import Config
from .benchmark import BenchmarkRunner, UVLOOP_AVAILABLE as BENCH_UVLOOP_AVAILABLE

console = Console()


def display_config():
    """Display configuration in a beautiful table."""
    table = Table(title="Configuration", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    config_data = Config.display()
    for key, value in config_data.items():
        table.add_row(key, str(value))
    
    # Add uvloop status
    uvloop_status = "✓ Available" if BENCH_UVLOOP_AVAILABLE else "✗ Not installed"
    table.add_row("uvloop", uvloop_status, style="green" if BENCH_UVLOOP_AVAILABLE else "yellow")
    
    console.print(table)


def display_results(results, baseline_approach="naive"):
    """Display benchmark results in beautiful tables."""
    # Group results by test name
    by_test = {}
    for r in results:
        if r.name not in by_test:
            by_test[r.name] = {}
        by_test[r.name][r.approach] = r
    
    # Results table
    table = Table(title="📊 Benchmark Results", box=box.DOUBLE, show_header=True, header_style="bold magenta")
    table.add_column("Test", style="cyan", no_wrap=True)
    table.add_column("Naive", justify="right", style="white")
    table.add_column("Threaded", justify="right", style="yellow")
    table.add_column("Async", justify="right", style="green")
    table.add_column("Best", justify="center", style="bold green")
    
    for test_name, approaches in by_test.items():
        naive_time = approaches.get("naive")
        threaded_time = approaches.get("threaded")
        async_time = approaches.get("async")
        
        # Format times
        naive_str = f"{naive_time.elapsed_time:.2f}s" if naive_time and naive_time.success else "N/A"
        threaded_str = f"{threaded_time.elapsed_time:.2f}s" if threaded_time and threaded_time.success else "N/A"
        async_str = f"{async_time.elapsed_time:.2f}s" if async_time and async_time.success else "N/A"
        
        # Find best
        times = []
        if naive_time and naive_time.success:
            times.append(("Naive", naive_time.elapsed_time))
        if threaded_time and threaded_time.success:
            times.append(("Threaded", threaded_time.elapsed_time))
        if async_time and async_time.success:
            times.append(("Async", async_time.elapsed_time))
        
        best = min(times, key=lambda x: x[1])[0] if times else "N/A"
        best_str = f"🏆 {best}"
        
        # Pretty test name
        test_display = test_name.replace("_", " ").title()
        
        table.add_row(test_display, naive_str, threaded_str, async_str, best_str)
    
    console.print(table)
    
    # Speedup table
    speedup_table = Table(title="⚡ Speedup vs Naive", box=box.ROUNDED, show_header=True, header_style="bold yellow")
    speedup_table.add_column("Test", style="cyan", no_wrap=True)
    speedup_table.add_column("Threaded", justify="right", style="yellow")
    speedup_table.add_column("Async", justify="right", style="green")
    
    for test_name, approaches in by_test.items():
        naive_time = approaches.get("naive")
        threaded_time = approaches.get("threaded")
        async_time = approaches.get("async")
        
        if not naive_time or not naive_time.success or naive_time.elapsed_time == 0:
            continue
        
        threaded_speedup = "N/A"
        if threaded_time and threaded_time.success and threaded_time.elapsed_time > 0:
            speedup = naive_time.elapsed_time / threaded_time.elapsed_time
            threaded_speedup = f"{speedup:.2f}x"
        
        async_speedup = "N/A"
        if async_time and async_time.success and async_time.elapsed_time > 0:
            speedup = naive_time.elapsed_time / async_time.elapsed_time
            async_speedup = f"{speedup:.2f}x"
        
        test_display = test_name.replace("_", " ").title()
        speedup_table.add_row(test_display, threaded_speedup, async_speedup)
    
    console.print(speedup_table)


@click.command()
@click.option(
    "--approach",
    "-a",
    multiple=True,
    type=click.Choice(["naive", "threaded", "async", "all"], case_sensitive=False),
    default=["all"],
    help="Which approach(es) to benchmark (default: all)"
)
@click.option(
    "--test",
    "-t",
    multiple=True,
    type=click.Choice(["seeding", "topk", "cursor", "all"], case_sensitive=False),
    default=["all"],
    help="Which test(s) to run (default: all)"
)
@click.option(
    "--docs",
    "-n",
    type=int,
    default=200_000,
    help="Number of documents to seed (default: 200,000)"
)
@click.option(
    "--index",
    type=str,
    default="idx:orders",
    help="Index name (default: idx:orders)"
)
@click.option(
    "--prefix",
    type=str,
    default="order:",
    help="Key prefix (default: order:)"
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode (minimal output)"
)
def main(approach, test, docs, index, prefix, quiet):
    """
    🚀 Redis RediSearch Performance Benchmark Tool
    
    Compare performance of naive, threaded, and async implementations
    for seeding and aggregation operations.
    """
    # Normalize inputs
    approaches = list(approach)
    if "all" in approaches:
        approaches = ["naive", "threaded"]
        if BENCH_UVLOOP_AVAILABLE:
            approaches.append("async")
    
    tests = list(test)
    if "all" in tests:
        tests = ["seeding", "topk", "cursor"]
    
    # Display header
    if not quiet:
        console.print(Panel.fit(
            "[bold cyan]Redis RediSearch Performance Benchmark[/bold cyan]",
            border_style="cyan"
        ))
        console.print()
        display_config()
        console.print()
    
    # Create benchmark runner
    runner = BenchmarkRunner(index=index, prefix=prefix, n_docs=docs)
    
    try:
        # Setup index
        if not quiet:
            with console.status("[bold green]Setting up index..."):
                state = runner.setup_index(recreate=True)
            console.print(f"✓ Index {state}", style="green")
            console.print()
        else:
            runner.setup_index(recreate=True)
        
        # Run benchmarks
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
            disable=quiet
        ) as progress:
            
            for test_name in tests:
                for app in approaches:
                    if test_name == "seeding":
                        task = progress.add_task(
                            f"[cyan]Seeding ({app})...",
                            total=None
                        )
                        result = runner.run_seeding(approach=app)
                        progress.remove_task(task)
                        
                        if not quiet:
                            if result.success:
                                console.print(f"✓ Seeding ({app}): {result.elapsed_time:.2f}s", style="green")
                            else:
                                console.print(f"✗ Seeding ({app}): {result.error}", style="red")
                    
                    elif test_name in ["topk", "cursor"]:
                        task = progress.add_task(
                            f"[cyan]Aggregation {test_name} ({app})...",
                            total=None
                        )
                        result = runner.run_aggregation(test_type=test_name, approach=app)
                        progress.remove_task(task)
                        
                        if not quiet:
                            if result.success:
                                console.print(f"✓ Aggregation {test_name} ({app}): {result.elapsed_time:.3f}s", style="green")
                            else:
                                console.print(f"✗ Aggregation {test_name} ({app}): {result.error}", style="red")
        
        # Display results
        if not quiet:
            console.print()
            display_results(runner.results)
        else:
            # Quiet mode: just print times
            for r in runner.results:
                if r.success:
                    print(f"{r.name},{r.approach},{r.elapsed_time:.3f}")
    
    finally:
        runner.cleanup()


if __name__ == "__main__":
    main()

