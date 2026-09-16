#!/usr/bin/env python3
"""
RoboStack environment activation command.
Opens a shell with robostack environment, DDS superclient config, and manager IP.
"""
import os
import sys
import subprocess
import tempfile
from typing import Optional
from colorama import Fore

from core.config import Config
from core.renderer import TemplateRenderer
from core.exceptions import ForgeError


def detect_package_manager() -> Optional[str]:
    """
    Detect which package manager is available (micromamba, mamba, or pixi).
    Returns the name of the first one found, or None if none are available.
    """
    managers = ['micromamba', 'mamba', 'pixi']

    for manager in managers:
        try:
            # For micromamba, check MAMBA_EXE environment variable first
            if manager == 'micromamba' and 'MAMBA_EXE' in os.environ:
                mamba_exe = os.environ['MAMBA_EXE']
                result = subprocess.run(
                    [mamba_exe, '--version'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    return manager

            # Standard detection for all managers
            result = subprocess.run(
                [manager, '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return manager
        except FileNotFoundError:
            continue

    return None


def check_environment_exists(manager: str, env_name: str) -> bool:
    """Check if an environment exists using the detected package manager."""
    try:
        # pixi uses a different command structure
        if manager == 'pixi':
            result = subprocess.run(
                ['pixi', 'info'],
                capture_output=True,
                text=True,
                check=False,
                cwd=os.getcwd()
            )
            # For pixi, we just check if pixi.toml exists and is valid
            return result.returncode == 0
        else:
            # micromamba and mamba use the same env list command
            # For micromamba, use MAMBA_EXE if available
            cmd = manager
            if manager == 'micromamba' and 'MAMBA_EXE' in os.environ:
                cmd = os.environ['MAMBA_EXE']

            result = subprocess.run(
                [cmd, 'env', 'list'],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse output to find environment name
            for line in result.stdout.split('\n'):
                if line.strip().startswith(env_name):
                    return True
            return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_manager_host(cfg: Config):
    """Get the manager host from config."""
    for host in cfg.hosts:
        if host.manager:
            return host
    return None


def verify_package_manager(manager: str) -> bool:
    """Verify that a specific package manager is installed."""
    try:
        # For micromamba, check MAMBA_EXE environment variable first
        if manager == 'micromamba' and 'MAMBA_EXE' in os.environ:
            mamba_exe = os.environ['MAMBA_EXE']
            result = subprocess.run(
                [mamba_exe, '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return True

        # Standard verification
        result = subprocess.run(
            [manager, '--version'],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def pixi_main(project_root: Optional[str] = None, env_name: str = "ros_env", config_file: str = 'config.yaml'):
    """
    Activate pixi/robostack environment with DDS configuration.

    Args:
        project_root: Path to project root
        env_name: Name of the robostack environment (default: "ros_env")
        config_file: Name or path to configuration file (default: 'config.yaml')
    """
    print(Fore.CYAN + "[pixi] Initializing robostack environment...")

    # 1) Verify pixi is available
    if not verify_package_manager('pixi'):
        print(Fore.RED + "[pixi] ERROR: pixi not found")
        print(Fore.YELLOW + "[pixi] Install pixi: https://pixi.sh/")
        sys.exit(1)
    manager = 'pixi'
    print(Fore.GREEN + "[pixi] ✓ pixi found")

    # 3) Load project config (moved up to get project root first)
    pr = os.path.abspath(project_root or ".")

    # 2) Check if we're in a pixi project (use project root, not cwd)
    pixi_toml = os.path.join(pr, 'pixi.toml')
    pyproject_toml = os.path.join(pr, 'pyproject.toml')
    if not os.path.exists(pixi_toml) and not os.path.exists(pyproject_toml):
        print(Fore.RED + f"[pixi] ERROR: Not in a pixi project (no pixi.toml or pyproject.toml found in {pr})")
        print(Fore.YELLOW + "[pixi] Initialize a pixi project with:")
        print(Fore.YELLOW + "  pixi init")
        print(Fore.YELLOW + "  pixi add ros-humble-desktop")
        sys.exit(1)
    print(Fore.GREEN + "[pixi] ✓ pixi project found")
    try:
        cfg = Config.load(pr, config_file=config_file)
    except FileNotFoundError:
        print(Fore.RED + f"[pixi] ERROR: config.yaml not found in {pr}")
        print(Fore.YELLOW + "[pixi] Run 'forge init' to create a project first")
        sys.exit(1)
    except Exception as e:
        print(Fore.RED + f"[pixi] ERROR: Failed to load config: {e}")
        sys.exit(1)

    print(Fore.GREEN + "[pixi] ✓ config loaded")

    # 4) Get manager host
    manager_host = get_manager_host(cfg)
    if not manager_host:
        print(Fore.RED + "[pixi] ERROR: No manager host found in config.yaml")
        print(Fore.YELLOW + "[pixi] Add 'manager: true' to one of your hosts")
        sys.exit(1)

    manager_ip = manager_host.effective_dds_ip
    print(Fore.GREEN + f"[pixi] ✓ manager host: {manager_host.name} ({manager_ip})")

    # 5) Configure RMW based on implementation type
    forge_dir = os.path.join(pr, '.forge')
    superclient_path = None
    zenoh_endpoint = None

    if cfg.is_zenoh:
        # Zenoh configuration
        zenoh_endpoint = f"tcp/{manager_ip}:{cfg.zenoh_router_port}"
        print(Fore.GREEN + f"[pixi] ✓ RMW: Zenoh (rmw_zenoh_cpp)")
        print(Fore.GREEN + f"[pixi] ✓ Zenoh router: {zenoh_endpoint}")
    else:
        # FastDDS configuration - check for superclient.xml
        superclient_path = os.path.join(forge_dir, 'superclient.xml')

        if not os.path.exists(superclient_path):
            print(Fore.YELLOW + f"[pixi] WARNING: superclient.xml not found at {superclient_path}")
            print(Fore.YELLOW + f"[pixi] Run 'forge stage' to generate it")
            print(Fore.YELLOW + f"[pixi] Continuing with ROS_DISCOVERY_SERVER only...")
            superclient_path = None
        else:
            print(Fore.GREEN + f"[pixi] ✓ Using superclient.xml from {superclient_path}")

    # 6) Create activation script and launch shell
    print(Fore.CYAN + "\n[pixi] Launching shell with robostack environment...")
    print(Fore.CYAN + f"[pixi] ROS_DOMAIN_ID: {cfg.ros_domain_id}")

    if cfg.is_zenoh:
        print(Fore.CYAN + f"[pixi] RMW_IMPLEMENTATION: rmw_zenoh_cpp")
        print(Fore.CYAN + f"[pixi] ZENOH_CONFIG_OVERRIDE: listen + connect to {zenoh_endpoint}")
    elif superclient_path:
        print(Fore.CYAN + f"[pixi] RMW_IMPLEMENTATION: rmw_fastrtps_cpp")
        print(Fore.CYAN + f"[pixi] FASTRTPS_DEFAULT_PROFILES_FILE: {superclient_path}")
        print(Fore.CYAN + f"[pixi] DDS Server: {manager_ip}:11811 (via superclient.xml)")
    else:
        print(Fore.CYAN + f"[pixi] RMW_IMPLEMENTATION: rmw_fastrtps_cpp")
        print(Fore.CYAN + f"[pixi] ROS_DISCOVERY_SERVER: {manager_ip}:11811")
    print(Fore.CYAN + "\n[pixi] Type 'exit' to close the robostack shell\n")

    # Build the RMW configuration lines
    if cfg.is_zenoh:
        rmw_config = f"""export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_ROUTER_CHECK_ATTEMPTS=10
export ZENOH_CONFIG_OVERRIDE='listen/endpoints=["tcp/0.0.0.0:0"];connect/endpoints=["{zenoh_endpoint}"]'"""
        middleware_info = f"Zenoh Router: {zenoh_endpoint}"
    elif superclient_path:
        # When using superclient.xml, don't set ROS_DISCOVERY_SERVER as it can conflict
        rmw_config = f"""export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE={superclient_path}"""
        middleware_info = f"DDS Server: {manager_ip}:11811"
    else:
        # Fallback to ROS_DISCOVERY_SERVER if no superclient.xml
        rmw_config = f"""export ROS_DISCOVERY_SERVER={manager_ip}:11811
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp"""
        middleware_info = f"DDS Server: {manager_ip}:11811"

    # Use a temporary directory for activation scripts
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pixi activation script
        activation_script = f"""
# Change to project directory where pixi.toml lives
cd "{pr}"

# Activate pixi environment
eval "$(pixi shell-hook)"

# Set ROS and RMW environment variables
export ROS_DOMAIN_ID={cfg.ros_domain_id}
export ROS_DISTRO={cfg.ros_distro}
{rmw_config}

# Stop ROS 2 daemon to avoid discovery conflicts
echo "Stopping ROS 2 daemon (to avoid discovery conflicts)..."
ros2 daemon stop 2>/dev/null || true

# Print info
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RoboStack Environment Active (pixi)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ROS Distribution: {cfg.ros_distro}"
echo "  ROS Domain ID:    {cfg.ros_domain_id}"
echo "  RMW:              {cfg.rmw_implementation_value}"
echo "  {middleware_info}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
"""

        # Write activation script to a temporary file
        script_path = os.path.join(tmpdir, 'activate.sh')
        with open(script_path, 'w') as f:
            f.write(activation_script)

        # Launch shell with the activation script
        shell = os.environ.get('SHELL', '/bin/bash')
        shell_name = os.path.basename(shell)

        try:
            if shell_name == 'zsh':
                # For zsh, create a ZDOTDIR with .zshrc
                zdotdir = os.path.join(tmpdir, 'zdotdir')
                os.makedirs(zdotdir, exist_ok=True)
                zshrc_path = os.path.join(zdotdir, '.zshrc')

                # Create .zshrc that sources the original and our script
                with open(zshrc_path, 'w') as f:
                    f.write(f"""
# Source original .zshrc if it exists
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc"
fi

# Source activation script
source {script_path}
""")

                # Launch zsh with custom ZDOTDIR
                env = os.environ.copy()
                env['ZDOTDIR'] = zdotdir
                subprocess.run(
                    [shell, '-i'],
                    env=env,
                    check=False
                )
            else:
                # For bash and other shells, use --rcfile if supported
                subprocess.run(
                    [shell, '--rcfile', script_path, '-i'],
                    check=False
                )
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n[pixi] Shell closed")

        print(Fore.GREEN + "\n[pixi] Robostack shell closed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m commands.pixi <project_root>", file=sys.stderr)
        sys.exit(1)

    pixi_main(project_root=sys.argv[1])
