#!/usr/bin/env python3
import os
import sys
import yaml
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from colorama import Fore
from core.config   import Config
from core.renderer import TemplateRenderer
from core.docker   import DockerHelper, is_localhost
from core.logger   import ComponentLogger
from core.models   import Component, Host
from python_on_whales.exceptions import DockerException
from utils.timing  import timed

def resolve_source_packages(comp: Component, cfg: Config) -> List[tuple]:
    """
    Resolve source paths into a list of (relative_path, package_name) tuples.
    These paths are relative to cfg.root and will be used directly in Docker COPY commands.
    """
    packages = []
    source_paths = comp.get_source_paths()

    for source_path in source_paths:
        abs_source = os.path.join(cfg.root, source_path)
        if not os.path.exists(abs_source):
            print(f"  - WARNING: Source path {source_path} does not exist")
            continue

        if not os.path.isdir(abs_source):
            print(f"  - WARNING: Source path {source_path} is not a directory")
            continue

        # Check if this is a ROS package
        if os.path.exists(os.path.join(abs_source, "package.xml")):
            package_name = os.path.basename(abs_source)
            packages.append((source_path, package_name))
            print(f"  - found package: {source_path} -> {package_name}")
        # Check if this is a workspace src directory containing packages
        elif os.path.exists(os.path.join(abs_source, "src")):
            src_contents = os.path.join(abs_source, "src")
            for pkg in os.listdir(src_contents):
                pkg_path = os.path.join(src_contents, pkg)
                if os.path.isdir(pkg_path) and os.path.exists(os.path.join(pkg_path, "package.xml")):
                    rel_pkg_path = os.path.join(source_path, "src", pkg)
                    packages.append((rel_pkg_path, pkg))
                    print(f"  - found package: {rel_pkg_path} -> {pkg}")
        else:
            print(f"  - WARNING: {source_path} doesn't appear to be a ROS package or workspace")

    return packages

def detect_component_features(comp: Component, cfg: Config) -> dict:
    has_common = bool(cfg.common_packages)
    has_repos  = bool(comp.repositories)
    has_apt    = bool(comp.apt_packages)

    # Resolve source packages (no copying, just detection)
    source_packages = resolve_source_packages(comp, cfg)
    has_local = bool(source_packages)

    print(f"[stage] Component '{comp.name}' features:")
    print(f"  - common_ws_exists: {has_common}")
    print(f"  - has_repos:        {has_repos}")
    print(f"  - comp_src_exists:  {has_local}")
    print(f"  - apt_exists:       {has_apt}")
    if source_packages:
        print(f"  - source_packages:  {len(source_packages)} packages")

    return {
        "common_ws_exists": has_common,
        "has_repos":        has_repos,
        "comp_src_exists":  has_local,
        "apt_exists":       has_apt,
        "source_packages":  source_packages
    }

def get_host(hosts_map: dict, comp: Component, cfg: Config) -> Host:
    if not comp.runs_on:
        sys.exit(f"[stage] ERROR: component '{comp.name}' missing 'runs_on'")
    host: Host = hosts_map.get(comp.runs_on)
    if not host:
        sys.exit(f"[stage] ERROR: runs_on '{comp.runs_on}' not defined")
    return host


def copy_component_sources(source_packages: List[tuple], cfg: Config, comp_dir: str):
    """
    Copy component source packages into the build context.
    Creates .forge/workspaces/<comp>/src/ with all source packages.

    Args:
        source_packages: List of (relative_path, package_name) tuples
        cfg: Config object
        comp_dir: Component's workspace directory (.forge/workspaces/<comp>/)
    """
    src_dir = os.path.join(comp_dir, "src")

    # Clean and recreate src directory
    if os.path.exists(src_dir):
        shutil.rmtree(src_dir)
    os.makedirs(src_dir, exist_ok=True)

    # Copy each source package
    for rel_path, pkg_name in source_packages:
        abs_source = os.path.join(cfg.root, rel_path)
        if os.path.exists(abs_source) and os.path.isdir(abs_source):
            dest = os.path.join(src_dir, pkg_name)
            print(f"  - copying {pkg_name}")
            shutil.copytree(abs_source, dest, symlinks=False)

def build_component_image(comp: Component,
                          cfg: Config,
                          hosts_map: dict,
                          base_tag: str,
                          renderer: TemplateRenderer,
                          docker: DockerHelper,
                          participant_id: int,
                          logger: Optional[ComponentLogger] = None) -> dict:

    host = get_host(hosts_map, comp, cfg)
    img_tag = comp.image_tag(cfg)
    platform = f"linux/{host.arch}"

    # Handle external pre-built images
    if comp.image:
        print(f"[stage] Using external image '{comp.name}' → {img_tag}")
        # No build needed, just use the external image
        return {
            "name": comp.name,
            "image": img_tag,
            "devices": comp.devices,
            "ports": comp.ports,
            "environment": comp.environment,
            "entrypoint": comp.entrypoint,
            "launch_args": comp.launch_args,
            "has_repos": False,
            "comp_src": False,
            "shm_size": comp.shm_size,
            "ipc_mode": comp.ipc_mode,
            "cpuset": comp.cpuset,
            "mount_shm": comp.mount_shm,
            "rt_enabled": comp.rt_enabled,
            "privileged": comp.privileged,
            "runtime": comp.runtime,
            "gpu_count": comp.gpu_count,
            "gpu_device_ids": comp.gpu_device_ids,
            "nvidia": comp.nvidia,
            "gui": comp.gui,
            "volumes": comp.volumes,
            "stdin_open": comp.stdin_open,
            "tty": comp.tty,
        }

    # Handle custom Dockerfile builds
    if comp.build:
        build_context = os.path.join(cfg.root, comp.build)
        dockerfile = os.path.join(build_context, "Dockerfile")

        if not os.path.exists(dockerfile):
            sys.exit(f"[stage] ERROR: Dockerfile not found at {dockerfile}")

        print(f"[stage] Building '{comp.name}' from custom Dockerfile → {img_tag} for [{platform}]")

        docker.build_multiarch(
            image_tag=img_tag,
            context=build_context,
            dockerfile=dockerfile,
            platforms=[platform],
            push=True,
            logger=logger
        )

        return {
            "name": comp.name,
            "image": img_tag,
            "devices": comp.devices,
            "ports": comp.ports,
            "environment": comp.environment,
            "entrypoint": comp.entrypoint,
            "launch_args": comp.launch_args,
            "has_repos": False,
            "comp_src": False,
            "shm_size": comp.shm_size,
            "ipc_mode": comp.ipc_mode,
            "cpuset": comp.cpuset,
            "mount_shm": comp.mount_shm,
            "rt_enabled": comp.rt_enabled,
            "privileged": comp.privileged,
            "runtime": comp.runtime,
            "gpu_count": comp.gpu_count,
            "gpu_device_ids": comp.gpu_device_ids,
            "nvidia": comp.nvidia,
            "gui": comp.gui,
            "volumes": comp.volumes,
            "stdin_open": comp.stdin_open,
            "tty": comp.tty,
        }

    # Forge-managed build (current logic)
    feats = detect_component_features(comp, cfg)

    # Working directory for generated files (Dockerfile, repos.yaml, superclient.xml)
    comp_dir = os.path.join(cfg.root, ".forge", "workspaces", comp.name)
    os.makedirs(comp_dir, exist_ok=True)

    # Find DDS manager host (default to first host if none specified)
    dds_manager = next((h for h in cfg.hosts if h.manager), None)
    if not dds_manager:
        if len(cfg.hosts) > 0:
            dds_manager = cfg.hosts[0]
            print(f"[stage] No host marked as manager, using '{dds_manager.name}' as DDS manager")
        else:
            sys.exit("[stage] ERROR: No hosts defined in config.")

    # Handle VCS repositories - write repos.yaml directly in comp_dir
    repos_file = os.path.join(comp_dir, "repos.yaml")
    if feats["has_repos"]:
        repo_map = {
            r.folder: {"type": "git", "url": r.url, "version": r.version}
            for r in comp.repositories
        }
        with open(repos_file, "w") as f:
            yaml.safe_dump({"repositories": repo_map}, f, default_flow_style=False, sort_keys=False)

    # Copy source packages into build context
    if feats["source_packages"]:
        copy_component_sources(feats["source_packages"], cfg, comp_dir)

    superclient_path = os.path.join(comp_dir, "superclient.xml")

    # Only generate superclient.xml when using FastDDS
    if cfg.is_fastdds:
        renderer.render_superclient(
            out_path=superclient_path,
            participantID=participant_id,
            this_host_ip=host.effective_dds_ip,
            dds_server_host_ip=dds_manager.effective_dds_ip
        )

    # Compute Zenoh router endpoint if using Zenoh
    zenoh_router_endpoint = None
    if cfg.is_zenoh:
        zenoh_router_endpoint = f"tcp/{dds_manager.effective_dds_ip}:{cfg.zenoh_router_port}"

    dockerfile_path = os.path.join(comp_dir, "Dockerfile")
    renderer.render_dockerfile(
        out_path=dockerfile_path,
        base_image=base_tag,
        ros_distro=cfg.ros_distro,
        ros_domain_id=cfg.ros_domain_id,
        comp=comp,
        source_packages=feats["source_packages"],
        repos_file="repos.yaml",  # Now relative to comp_dir
        superclient_path="superclient.xml" if cfg.is_fastdds else "",  # Now relative to comp_dir
        apt_packages=comp.apt_packages or [],
        pip_packages=comp.pip_packages or [],
        postinstall=comp.postinstall or [],
        has_repos=feats["has_repos"],
        comp_src_exists=feats["comp_src_exists"],
        enable_apt_caching=cfg.enable_apt_caching,
        dds_server_ip=dds_manager.effective_dds_ip,
        rmw_implementation=cfg.rmw_implementation,
        zenoh_router_endpoint=zenoh_router_endpoint
    )

    if not os.path.isfile(dockerfile_path):
        sys.exit(f"[stage] ERROR: {dockerfile_path} missing after render")

    img_tag = comp.image_tag(cfg)
    platform = f"linux/{host.arch}"

    # Check if we should build on device
    if host.build_on_device and not is_localhost(host):
        print(f"[stage] Building '{comp.name}' → {img_tag} on device {host.name} ({host.arch})")
        docker.build_on_remote_host(
            host=host,
            image_tag=img_tag,
            context=comp_dir,
            dockerfile=dockerfile_path,
            push=False
        )
    else:
        print(f"[stage] Building '{comp.name}' → {img_tag} for [{platform}]")
        # Use comp_dir as context (self-contained build context)
        docker.build_multiarch(
            image_tag=img_tag,
            context=comp_dir,
            dockerfile=dockerfile_path,
            platforms=[platform],
            push=True,
            logger=logger
        )

    return {
        "name": comp.name,
        "image": img_tag,
        "devices": comp.devices,
        "ports": comp.ports,
        "environment": comp.environment,
        "entrypoint": comp.entrypoint,
        "launch_args": comp.launch_args,
        "has_repos": feats["has_repos"],
        "comp_src": feats["comp_src_exists"],
        "shm_size": comp.shm_size,
        "ipc_mode": comp.ipc_mode,
        "cpuset": comp.cpuset,
        "mount_shm": comp.mount_shm,
        "rt_enabled": comp.rt_enabled,
        "privileged": comp.privileged,
        "runtime": comp.runtime,
        "gpu_count": comp.gpu_count,
        "gpu_device_ids": comp.gpu_device_ids,
        "nvidia": comp.nvidia,
        "gui": comp.gui,
        "volumes": comp.volumes,
        "stdin_open": comp.stdin_open,
        "tty": comp.tty,
    }

def stage_main(project_root: str,
               component: Optional[str] = None,
               refresh: bool = False,
               force_base: bool = False,
               no_pull: bool = False,
               jobs: int = 1,
               config_file: str = 'config.yaml'):
    with timed("stage"):
        _stage_main_impl(project_root, component, refresh, force_base, no_pull, jobs, config_file)


def _stage_main_impl(project_root: str,
                     component: Optional[str],
                     refresh: bool,
                     force_base: bool,
                     no_pull: bool,
                     jobs: int,
                     config_file: str):
    project_root = os.path.abspath(project_root)
    os.chdir(project_root)

    cfg = Config.load(project_root, config_file=config_file)
    hosts_map = {h.name: h for h in cfg.hosts}

    # Filter components for building (may be single component with -c)
    comps_to_build = cfg.filter_components(name=component)
    if not comps_to_build:
        sys.exit(f"[stage] ERROR: no components to stage (filter={component})")

    # All components (for compose file generation)
    all_comps = cfg.components
    comps_to_build_names = {c.name for c in comps_to_build}

    tpl_dir = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'templates'))
    renderer = TemplateRenderer(tpl_dir)
    docker = DockerHelper()

    # Group ALL components per host (for compose files)
    all_components_by_host = defaultdict(list)
    for comp in all_comps:
        all_components_by_host[comp.runs_on].append(comp)

    base_tag = cfg.base_image

    # If refresh mode, skip all building and just regenerate compose files
    if refresh:
        print("[stage] Refresh mode: skipping builds, regenerating compose files only")
    else:
        # Build base image once for all platforms
        from commands.prepare_base import prepare_base_main
        prepare_base_main(project_root, config_file=config_file, force=force_base)

        # Cap parallelism to the number of components and at least 1
        max_workers = max(1, min(jobs, len(comps_to_build)))
        use_parallel = max_workers > 1

        def _build_one(comp: Component):
            host = hosts_map[comp.runs_on]
            participant_id = 2  # TODO: proper participant ID
            logger = ComponentLogger(comp.name) if use_parallel else None
            build_component_image(
                comp, cfg, hosts_map, base_tag, renderer, docker,
                participant_id=participant_id,
                logger=logger,
            )
            # Skip pull if building on device (image is already there) or --no-pull
            if no_pull:
                return
            if host.build_on_device and not is_localhost(host):
                return
            try:
                docker.pull_image_on_host(host, base_tag)
            except DockerException:
                print(Fore.RED + f"[stage] Failed to pull base image on host '{host.name}' ({host.ip})", file=sys.stderr)
                raise

        if use_parallel:
            print(f"[stage] Building {len(comps_to_build)} components in parallel (jobs={max_workers})")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_build_one, comp): comp for comp in comps_to_build}
                first_error: Optional[BaseException] = None
                for future in as_completed(futures):
                    comp = futures[future]
                    try:
                        future.result()
                    except BaseException as e:
                        print(Fore.RED + f"[stage] Build failed for '{comp.name}': {e}", file=sys.stderr)
                        if first_error is None:
                            first_error = e
                if first_error is not None:
                    raise first_error
        else:
            for comp in comps_to_build:
                _build_one(comp)

    # Generate staged entries for ALL components (for compose files)
    staged_by_host = {}
    for host_name, host_comps in all_components_by_host.items():
        staged = []
        for j, comp in enumerate(host_comps):
            feats = detect_component_features(comp, cfg)
            staged.append({
                "name": comp.name,
                "image": comp.image_tag(cfg),
                "devices": comp.devices,
                "ports": comp.ports,
                "environment": comp.environment,
                "entrypoint": comp.entrypoint,
                "launch_args": comp.launch_args,
                "has_repos": feats["has_repos"],
                "comp_src": feats["comp_src_exists"],
                "shm_size": comp.shm_size,
                "ipc_mode": comp.ipc_mode,
                "cpuset": comp.cpuset,
                "mount_shm": comp.mount_shm,
                "rt_enabled": comp.rt_enabled,
                "privileged": comp.privileged,
                "runtime": comp.runtime,
                "gpu_count": comp.gpu_count,
                "gpu_device_ids": comp.gpu_device_ids,
                "nvidia": comp.nvidia,
                "gui": comp.gui,
                "volumes": comp.volumes,
                "stdin_open": comp.stdin_open,
                "tty": comp.tty,
            })
        staged_by_host[host_name] = staged

    # Find manager host (used for DDS server or Zenoh router)
    manager_host = next((h for h in cfg.hosts if h.manager), None)
    if not manager_host and len(cfg.hosts) > 0:
        manager_host = cfg.hosts[0]

    # Write one docker-compose.<host>.yaml per host
    for host_name, staged_comps in staged_by_host.items():
        host = hosts_map[host_name]
        compose_name = f"docker-compose.{host_name}.yaml"
        out_path = os.path.join(".", compose_name)
        # Check if this host uses build_on_device
        build_on_device = host.build_on_device and not is_localhost(host)
        renderer.render_compose(out_path, staged_comps, cfg, host=host, build_on_device=build_on_device)
        print(f"[stage] Wrote '{compose_name}'")

    # Generate local development config based on RMW implementation
    if manager_host:
        forge_dir = os.path.join(project_root, '.forge')
        os.makedirs(forge_dir, exist_ok=True)

        if cfg.is_fastdds:
            # Generate superclient.xml for local development (FastDDS)
            superclient_path = os.path.join(forge_dir, 'superclient.xml')

            # Get local IP for DDS communication
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((manager_host.effective_dds_ip, 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "127.0.0.1"

            renderer.render_superclient(
                superclient_path,
                participantID=1,  # Local dev machine uses participant ID 1
                this_host_ip=local_ip,
                dds_server_host_ip=manager_host.effective_dds_ip
            )
            print(Fore.GREEN + f"[stage] ✓ Generated superclient.xml for local development")
            print(Fore.CYAN + f"[stage]   Location: {superclient_path}")
            print(Fore.CYAN + f"[stage]   DDS Server: {manager_host.effective_dds_ip}:11811")
        elif cfg.is_zenoh:
            # Print Zenoh router info for local development
            zenoh_endpoint = f"tcp/{manager_host.effective_dds_ip}:{cfg.zenoh_router_port}"
            print(Fore.GREEN + f"[stage] ✓ Zenoh RMW configured")
            print(Fore.CYAN + f"[stage]   Zenoh Router: {zenoh_endpoint}")
            print(Fore.CYAN + f"[stage]   For local development, set:")
            print(Fore.CYAN + f"[stage]     export RMW_IMPLEMENTATION=rmw_zenoh_cpp")
            print(Fore.CYAN + f"[stage]     export ZENOH_ROUTER={zenoh_endpoint}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--project-root", default=".", help="Path to project root")
    parser.add_argument("-c", "--component", default=None, help="Component to restage")
    parser.add_argument("--refresh", action="store_true", help="Only regenerate docker-compose.yml")
    parser.add_argument("--force-base", action="store_true", help="Force rebuild of base image")
    parser.add_argument("--no-pull", action="store_true", help="Skip pulling images on hosts after build")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="Max number of components to build in parallel")
    args = parser.parse_args()
    stage_main(args.project_root, args.component, args.refresh, args.force_base,
               no_pull=args.no_pull, jobs=args.jobs)
