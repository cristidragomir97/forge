#!/usr/bin/env python3
import os
import sys
import shutil
import yaml
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Tuple

from python_on_whales import DockerClient
from colorama import Fore
from core.config   import Config
from core.docker   import is_localhost
from core.logger   import ComponentLogger
from core.models   import Component, Host
from utils.timing  import timed

def _log(logger: Optional[ComponentLogger], msg: str):
    if logger:
        logger.info(msg)
    else:
        print(msg)

def _err(logger: Optional[ComponentLogger], msg: str):
    if logger:
        logger.error(msg)
    else:
        print(Fore.RED + msg, file=sys.stderr)

def get_host_arch() -> str:
    """Get the current machine's architecture in Docker format."""
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        return 'amd64'
    elif machine in ('aarch64', 'arm64'):
        return 'arm64'
    elif machine.startswith('arm'):
        return 'armv7'
    return machine

def get_host(hosts_map: dict, comp: Component, cfg: Config) -> Host:
    """Get the host for a component based on runs_on."""
    if not comp.runs_on:
        sys.exit(f"[build] ERROR: component '{comp.name}' missing 'runs_on'")
    host = hosts_map.get(comp.runs_on)
    if not host:
        sys.exit(f"[build] ERROR: runs_on '{comp.runs_on}' not defined")
    return host

def resolve_source_packages(comp: Component, cfg: Config) -> List[Tuple[str, str]]:
    """
    Resolve source paths into a list of (absolute_path, package_name) tuples.
    """
    packages = []
    source_paths = comp.get_source_paths()

    for source_path in source_paths:
        abs_source = os.path.join(cfg.root, source_path)
        if not os.path.exists(abs_source):
            continue

        if not os.path.isdir(abs_source):
            continue

        # Check if this is a ROS package
        if os.path.exists(os.path.join(abs_source, "package.xml")):
            package_name = os.path.basename(abs_source)
            packages.append((abs_source, package_name))
        # Check if this is a workspace src directory containing packages
        elif os.path.exists(os.path.join(abs_source, "src")):
            src_contents = os.path.join(abs_source, "src")
            for pkg in os.listdir(src_contents):
                pkg_path = os.path.join(src_contents, pkg)
                if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "package.xml")):
                    packages.append((pkg_path, pkg))

    return packages

def _run_streamed(cmd: List[str], logger: ComponentLogger) -> int:
    """Run a subprocess and stream its output line-by-line through the logger."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )
    for line in process.stdout:
        logger.log_line(line.rstrip())
    process.wait()
    return process.returncode

def build_on_remote(comp: Component, cfg: Config, host: Host, source_packages: List[Tuple[str, str]],
                    logger: Optional[ComponentLogger] = None):
    """
    Build a component on a remote host.
    1) Rsync source packages to remote host
    2) Run docker build command via SSH
    3) Leave build artifacts on remote (used by launch)
    """
    comp_name = comp.name
    remote_build_root = f"{host.effective_mount_root}/{comp_name}/{cfg.workspace_dir}"
    remote_src = f"{remote_build_root}/src"

    _log(logger, f"[build:{comp_name}] Building on device {host.name} ({host.ip})")

    # Create remote directory structure
    ssh_prefix = f"{host.user}@{host.ip}"
    subprocess.run(
        ["ssh", ssh_prefix, f"mkdir -p {remote_src}"],
        check=True
    )

    # Rsync each source package to remote
    _log(logger, f"[build:{comp_name}] Syncing {len(source_packages)} packages to {host.name}...")
    for abs_source, pkg_name in source_packages:
        remote_dest = f"{ssh_prefix}:{remote_src}/{pkg_name}/"
        subprocess.run(
            ["rsync", "-az", "--delete", "-e", "ssh", f"{abs_source}/", remote_dest],
            check=True
        )
        _log(logger, f"  - synced {pkg_name}")

    # Build command
    post_hooks = comp.postinstall or []
    cmds = [
        "source /opt/ros/$ROS_DISTRO/setup.bash",
        "colcon build --symlink-install --install-base install"
    ]
    for p in post_hooks:
        cmds.append(
            "source /opt/ros/$ROS_DISTRO/setup.bash && "
            "source /ros_ws/install/setup.bash && "
            f"{p}"
        )
    full_cmd = " && ".join(cmds)

    # Run build via remote Docker
    image = comp.image_tag(cfg)
    docker_url = f"tcp://{host.ip}:{host.port}"

    _log(logger, f"[build:{comp_name}] Running build on {host.name}...")
    docker_cmd = [
        "docker", "-H", docker_url, "run", "--rm",
        "-v", f"{remote_build_root}:/ros_ws:rw",
        "-w", "/ros_ws",
        "-e", f"ROS_DISTRO={cfg.ros_distro}",
        image,
        "bash", "-lc", full_cmd
    ]

    if logger:
        rc = _run_streamed(docker_cmd, logger)
    else:
        rc = subprocess.run(docker_cmd).returncode
    if rc != 0:
        _err(logger, f"[build:{comp_name}] Build failed on {host.name}")
        sys.exit(1)

    _log(logger, f"[build:{comp_name}] Done (artifacts at {host.name}:{remote_build_root}/install)")


def build_one_component(comp: Component, cfg: Config, hosts_map: dict, host_arch: str,
                         build_root: str, docker: DockerClient,
                         logger: Optional[ComponentLogger] = None):
    """Build a single component (handles both on-device and local builds)."""
    # Check if this component's host wants on-device builds
    host = hosts_map.get(comp.runs_on)
    if host and host.build_on_device and not is_localhost(host):
        source_packages = resolve_source_packages(comp, cfg)
        if not source_packages:
            _log(logger, f"[build] Skipping '{comp.name}' (no source packages found)")
            return
        build_on_remote(comp, cfg, host, source_packages, logger=logger)
        return

    comp_name = comp.name

    # Resolve source packages
    source_packages = resolve_source_packages(comp, cfg)

    # only build if there's local source
    if not source_packages:
        _log(logger, f"[build] Skipping '{comp_name}' (no source packages found)")
        return

    # prepare a clean workspace
    ws_root = os.path.join(build_root, comp_name, cfg.workspace_dir)
    ws_src = os.path.join(ws_root, 'src')

    # copy in your sources
    _log(logger, f"[build] Copying {len(source_packages)} packages for '{comp_name}' → {ws_src}")
    if os.path.exists(ws_src):
        shutil.rmtree(ws_src)
    os.makedirs(ws_src, exist_ok=True)

    for abs_source, pkg_name in source_packages:
        dest = os.path.join(ws_src, pkg_name)
        _log(logger, f"  - copying {pkg_name}")
        shutil.copytree(abs_source, dest, symlinks=False)

    # load any post-install hooks
    post_hooks = comp.postinstall or []

    # assemble the build command
    cmds = [
        "source /opt/ros/$ROS_DISTRO/setup.bash",
        "colcon build --symlink-install --install-base install"
    ]
    for p in post_hooks:
        cmds.append(
            "source /opt/ros/$ROS_DISTRO/setup.bash && "
            "source /ros_ws/install/setup.bash && "
            f"{p}"
        )
    full_cmd = " && ".join(cmds)

    # Determine target platform for potential emulation
    host = get_host(hosts_map, comp, cfg)
    target_arch = host.arch
    target_platform = f"linux/{target_arch}"

    if target_arch != host_arch:
        _log(logger, f"[build] [{comp_name}] Cross-compiling: {host_arch} → {target_arch} (using emulation)")

    _log(logger, f"[build] [{comp_name}] Running build container:")
    _log(logger, f"         {full_cmd}")

    # run the unified builder image (created in stage)
    image = comp.image_tag(cfg)

    # Pull image with correct platform if cross-compiling
    if target_arch != host_arch:
        _log(logger, f"[build] [{comp_name}] Pulling image for {target_platform}...")
        docker.image.pull(image, platform=target_platform)

    if logger:
        # Stream via subprocess so output stays prefixed under parallel builds.
        # No -t (TTY) since multiple parallel containers can't share the terminal.
        docker_cmd = [
            "docker", "run", "--rm", "-i",
            "--platform", target_platform,
            "-w", "/ros_ws",
            "-e", f"ROS_DISTRO={cfg.ros_distro}",
            "-v", f"{os.path.abspath(ws_root)}:/ros_ws:rw",
            image,
            "bash", "-lc", full_cmd,
        ]
        rc = _run_streamed(docker_cmd, logger)
        if rc != 0:
            _err(logger, f"[build] '{comp_name}' build failed (exit {rc})")
            raise subprocess.CalledProcessError(rc, docker_cmd)
    else:
        docker.run(
            image       = image,
            command     = ["bash", "-lc", full_cmd],
            remove      = True,
            tty         = True,
            workdir     = "/ros_ws",
            envs        = {"ROS_DISTRO": cfg.ros_distro},
            volumes     = [(os.path.abspath(ws_root), "/ros_ws", "rw")],
            platform    = target_platform,
        )

    _log(logger, f"[build] '{comp_name}' done; install at {ws_root}/install")


def build_main(project_root: str, component: Optional[str] = None, jobs: int = 1,
               config_file: str = 'config.yaml'):
    """
    For each component that has local source packages:
      1) Copy sources → build/<comp>/ros_ws/src
      2) Run any postinstall hooks
      3) Invoke the builder image (already staged) to colcon build → install

    If the target host has build_on_device=true, the build runs on the remote device.
    With jobs > 1, components are built concurrently.
    """
    with timed("build"):
        _build_main_impl(project_root, component, jobs, config_file)


def _build_main_impl(project_root: str, component: Optional[str], jobs: int, config_file: str):
    # 1) chdir into project
    project_root = os.path.abspath(project_root)
    os.chdir(project_root)

    # 2) load config & pick components
    cfg   = Config.load(project_root, config_file=config_file)
    docker = DockerClient()
    hosts_map = {h.name: h for h in cfg.hosts}
    comps = cfg.filter_components(name=component)
    host_arch = get_host_arch()
    if not comps:
        print(f"[build] No components to build (filter={component})")
        return

    build_root = os.path.abspath(cfg.build_dir)
    os.makedirs(build_root, exist_ok=True)

    max_workers = max(1, min(jobs, len(comps)))
    use_parallel = max_workers > 1

    if use_parallel:
        print(f"[build] Building {len(comps)} components in parallel (jobs={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    build_one_component, comp, cfg, hosts_map, host_arch,
                    build_root, docker, ComponentLogger(comp.name)
                ): comp for comp in comps
            }
            first_error: Optional[BaseException] = None
            for future in as_completed(futures):
                comp = futures[future]
                try:
                    future.result()
                except BaseException as e:
                    print(Fore.RED + f"[build] '{comp.name}' failed: {e}", file=sys.stderr)
                    if first_error is None:
                        first_error = e
            if first_error is not None:
                raise first_error
    else:
        for comp in comps:
            build_one_component(comp, cfg, hosts_map, host_arch, build_root, docker, logger=None)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--project-root", default=".", help="Path to project root")
    parser.add_argument("-c", "--component", default=None, help="Component to build")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="Max number of components to build in parallel")
    args = parser.parse_args()
    build_main(args.project_root, args.component, jobs=args.jobs)
