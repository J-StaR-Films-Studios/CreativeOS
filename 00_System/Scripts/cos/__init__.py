"""
CreativeOS — Your Creative Nervous System.
One CLI to rule your entire creative workflow.
"""

__version__ = "2.1.0"
__author__ = "J Star Films"

def main() -> None:
    """Load the CLI only when invoked so first-run help works without config."""
    from .cli import main as cli_main

    cli_main()


__all__ = ["main", "__version__"]
