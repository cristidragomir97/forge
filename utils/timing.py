"""Timing utilities for CLI commands."""
import time
from contextlib import contextmanager
from colorama import Fore, Style


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {secs:.0f}s"


@contextmanager
def timed(label: str):
    """Print elapsed time for the wrapped block, even on failure."""
    start = time.monotonic()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed = time.monotonic() - start
        status = f"{Fore.RED}failed" if failed else f"{Fore.GREEN}done"
        print(f"{status} {Fore.CYAN}[{label}]{Style.RESET_ALL} took {Fore.YELLOW}{format_duration(elapsed)}{Style.RESET_ALL}")
