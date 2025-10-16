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
from .schema import load_schema

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


def display_schema(schema):
    """Display schema information in a beautiful table."""
    table = Table(title="📋 Schema", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Index Name", schema.index.name)
    table.add_row("Prefix", schema.index.prefix)
    table.add_row("Storage Type", schema.index.storage_type.upper())
    table.add_row("Fields", str(len(schema.fields)))
    table.add_row("Aggregation Fields", ", ".join(schema.get_aggregation_fields()))

    console.print(table)

    # Fields table
    fields_table = Table(title="🔧 Fields", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    fields_table.add_column("Name", style="cyan", no_wrap=True)
    fields_table.add_column("Type", style="yellow")
    fields_table.add_column("Generator", style="green")

    for field in schema.fields:
        fields_table.add_row(field.name, field.type.upper(), field.generator or "(default)")

    console.print(fields_table)


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
    "--schema",
    "-s",
    type=click.Path(exists=True),
    default="schemas/ecommerce.yaml",
    help="Path to schema YAML file (default: schemas/ecommerce.yaml)"
)
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
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode (minimal output)"
)
def main(schema, approach, test, docs, quiet):
    """
    🚀 Redis RediSearch Performance Benchmark Tool

    Schema-driven benchmarking for seeding and aggregation operations.
    Compare performance of naive, threaded, and async implementations.
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

    # Load schema
    try:
        schema_obj = load_schema(schema)
    except Exception as e:
        console.print(f"[red]✗ Failed to load schema: {e}[/red]")
        return

    # Display header
    if not quiet:
        console.print(Panel.fit(
            "[bold cyan]Redis RediSearch Performance Benchmark[/bold cyan]",
            border_style="cyan"
        ))
        console.print()
        display_config()
        console.print()
        display_schema(schema_obj)
        console.print()

    # Create benchmark runner
    runner = BenchmarkRunner(schema=schema_obj, schema_path=schema, n_docs=docs)
    
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

