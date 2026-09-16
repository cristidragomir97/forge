"""
Colored logging utility with component name prefixes.

Provides consistent, colored logging across build and stage operations.
"""

import sys
from colorama import Fore, Style


class ComponentLogger:
    """Logger that prefixes all output with a colored component name."""

    # Colors to use for different components (avoiding red and yellow as requested)
    COLORS = [
        Fore.BLUE,
        Fore.MAGENTA,
        Fore.CYAN,
        Fore.GREEN,
        Fore.LIGHTBLUE_EX,
        Fore.LIGHTMAGENTA_EX,
        Fore.LIGHTCYAN_EX,
        Fore.LIGHTGREEN_EX,
    ]

    _color_index = 0
    _component_colors = {}

    @classmethod
    def _get_color_for_component(cls, component_name: str) -> str:
        """Get a consistent color for a component name."""
        if component_name not in cls._component_colors:
            cls._component_colors[component_name] = cls.COLORS[cls._color_index % len(cls.COLORS)]
            cls._color_index += 1
        return cls._component_colors[component_name]

    def __init__(self, component_name: str):
        """Initialize logger for a specific component."""
        self.component_name = component_name
        self.color = self._get_color_for_component(component_name)
        self.prefix = f"{self.color}[{component_name}]{Style.RESET_ALL} "

    def log(self, message: str, file=sys.stdout):
        """Log a message with the component prefix."""
        # Handle multi-line messages
        for line in message.splitlines():
            print(f"{self.prefix}{line}", file=file)

    def log_line(self, line: str, file=sys.stdout):
        """Log a single line with the component prefix (no automatic newline handling)."""
        print(f"{self.prefix}{line}", file=file, flush=True)

    def info(self, message: str):
        """Log an info message."""
        self.log(message)

    def warning(self, message: str):
        """Log a warning message."""
        self.log(f"{Fore.YELLOW}WARNING:{Style.RESET_ALL} {message}", file=sys.stderr)

    def error(self, message: str):
        """Log an error message."""
        self.log(f"{Fore.RED}ERROR:{Style.RESET_ALL} {message}", file=sys.stderr)

    def success(self, message: str):
        """Log a success message."""
        self.log(f"{Fore.GREEN}✓{Style.RESET_ALL} {message}")


class StreamPrefixer:
    """Utility to prefix lines from a stream with component name."""

    def __init__(self, logger: ComponentLogger):
        self.logger = logger
        self.buffer = ""

    def write(self, data: str):
        """Process and prefix incoming data."""
        self.buffer += data
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line:  # Don't print empty lines
                self.logger.log_line(line)

    def flush(self):
        """Flush any remaining buffered data."""
        if self.buffer:
            self.logger.log_line(self.buffer)
            self.buffer = ""
