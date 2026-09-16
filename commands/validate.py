#!/usr/bin/env python3
"""
Validate configuration file without executing any operations.

Useful for checking config syntax and validating source paths before running
stage, build, or deploy commands.
"""

import os
import sys
from colorama import Fore

from core.validation import ConfigValidator
from core.exceptions import ConfigurationError, SourceNotFoundError, ValidationError


def validate_main(project_root: str, config_file: str = 'config.yaml'):
    """
    Validate forge configuration.

    Args:
        project_root: Path to project directory
        config_file: Name or path to configuration file (default: 'config.yaml')

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    project_root = os.path.abspath(project_root)

    # Support both absolute paths and relative paths
    if os.path.isabs(config_file):
        config_path = config_file
    else:
        config_path = os.path.join(project_root, config_file)

    print(f"[validate] Checking configuration in {project_root}")

    validator = ConfigValidator(project_root)

    try:
        # Run all validation checks
        config, warnings = validator.validate_all(config_path)

        # Print warnings
        if warnings:
            print(Fore.YELLOW + f"\n[validate] Found {len(warnings)} warning(s):")
            for warning in warnings:
                print(Fore.YELLOW + f"  ⚠ {warning}")

        # Print success summary
        print(Fore.GREEN + f"\n[validate] ✓ Configuration is valid")
        print(f"  - ROS Distribution: {config.ros_distro}")
        print(f"  - Components: {len(config.components)}")
        print(f"  - Hosts: {len(config.hosts)}")
        print(f"  - Common Packages: {len(config.common_packages)}")

        # List components and their hosts
        if config.components:
            print(f"\n[validate] Components:")
            for comp in config.components:
                host_info = f" → {comp.runs_on}" if comp.runs_on else " (simulation)"
                sources_info = ""
                if comp.sources:
                    sources_info = f" ({len(comp.sources)} sources)"
                elif comp.source:
                    sources_info = f" (1 source)"
                print(f"  - {comp.name}{host_info}{sources_info}")

        # List hosts
        if config.hosts:
            print(f"\n[validate] Hosts:")
            for host in config.hosts:
                manager_info = " [DDS Manager]" if host.manager else ""
                print(f"  - {host.name} ({host.user}@{host.ip}) [{host.arch}]{manager_info}")

        return 0

    except (ConfigurationError, SourceNotFoundError, ValidationError) as e:
        print(Fore.RED + f"\n[validate] ✗ Validation failed:")
        print(Fore.RED + f"  {e}")

        if hasattr(e, 'context') and e.context:
            # Special handling for multiple errors
            if 'errors' in e.context:
                errors = e.context['errors']
                print(Fore.RED + f"\n[validate] Found {len(errors)} validation error(s):")
                for i, error in enumerate(errors, 1):
                    print(Fore.RED + f"  {i}. {error}")
            else:
                print(Fore.RED + f"\n[validate] Additional context:")
                for key, value in e.context.items():
                    print(Fore.RED + f"  - {key}: {value}")

        return 1

    except FileNotFoundError as e:
        print(Fore.RED + f"\n[validate] ✗ Config file not found:")
        print(Fore.RED + f"  {e}")
        return 1

    except Exception as e:
        print(Fore.RED + f"\n[validate] ✗ Unexpected error:")
        print(Fore.RED + f"  {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    pr = args[0] if len(args) >= 1 else "."
    sys.exit(validate_main(pr))
