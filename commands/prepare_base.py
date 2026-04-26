# commands/prepare_base.py
from core.config import Config
from core.renderer import TemplateRenderer
from core.docker import DockerHelper, is_localhost
from colorama import Fore
import os
import sys
import shutil
import hashlib
import platform

def compute_base_hash(cfg: Config, project_root: str) -> str:
    """Compute hash of base image inputs to detect changes."""
    hasher = hashlib.sha256()

    # Hash ROS distro and tag
    hasher.update(cfg.ros_distro.encode())
    hasher.update(cfg.tag.encode())

    # Hash common packages configuration
    for pkg in cfg.common_packages:
        hasher.update(pkg.name.encode())
        if pkg.repositories:
            for repo in pkg.repositories:
                hasher.update(repo.url.encode())
                hasher.update(repo.version.encode())
        if pkg.source:
            # Handle both string and list sources
            if isinstance(pkg.source, list):
                for src in pkg.source:
                    hasher.update(src.encode())
            else:
                hasher.update(pkg.source.encode())

    # Hash apt packages
    for apt_pkg in cfg.apt_packages:
        hasher.update(apt_pkg.encode())

    # Hash common package source files if they're local
    for pkg in cfg.common_packages:
        if pkg.source:
            # Handle both string and list sources
            sources = pkg.source if isinstance(pkg.source, list) else [pkg.source]
            for src in sources:
                source_path = os.path.join(project_root, src)
                if os.path.exists(source_path):
                    # Hash package.xml if it exists (contains version/dependencies)
                    pkg_xml = os.path.join(source_path, "package.xml")
                    if os.path.exists(pkg_xml):
                        with open(pkg_xml, 'rb') as f:
                            hasher.update(f.read())

    return hasher.hexdigest()

def load_base_hash(base_dir: str) -> str:
    """Load previously stored base image hash."""
    hash_file = os.path.join(base_dir, "base.hash")
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            return f.read().strip()
    return ""

def save_base_hash(base_dir: str, hash_value: str):
    """Save base image hash."""
    hash_file = os.path.join(base_dir, "base.hash")
    with open(hash_file, 'w') as f:
        f.write(hash_value)

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


def copy_common_sources(cfg: Config, project_root: str, base_dir: str):
    """
    Copy local common package sources into the build context.
    Creates .forge/base/src/ with all local source packages.
    """
    src_dir = os.path.join(base_dir, "src")

    # Clean and recreate src directory
    if os.path.exists(src_dir):
        shutil.rmtree(src_dir)
    os.makedirs(src_dir, exist_ok=True)

    # Copy each local source package
    for pkg in cfg.common_packages:
        if pkg.is_local_based and pkg.source:
            sources = pkg.source if isinstance(pkg.source, list) else [pkg.source]
            for src_path in sources:
                abs_source = os.path.join(project_root, src_path)
                if os.path.exists(abs_source) and os.path.isdir(abs_source):
                    # Get package name from path
                    pkg_name = os.path.basename(abs_source.rstrip('/'))
                    dest = os.path.join(src_dir, pkg_name)
                    print(f"[prepare_base] Copying common package: {src_path} -> src/{pkg_name}")
                    shutil.copytree(abs_source, dest, symlinks=False)


def prepare_base_main(project_root: str, config_file: str = 'config.yaml', force: bool = False):
    cfg = Config.load(project_root, config_file=config_file)
    tpl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    renderer = TemplateRenderer(tpl_dir)
    docker = DockerHelper()

    # Map ROS distro to Ubuntu release
    ubuntu_map = {
        "jazzy": "noble",
        "humble": "jammy",
        "galactic": "jammy",
        "foxy": "focal"
    }
    ubuntu = ubuntu_map.get(cfg.ros_distro, "jammy")

    # Generate Dockerfile.base and prepare build context
    base_dir = os.path.join(project_root, ".forge", "base")
    os.makedirs(base_dir, exist_ok=True)
    base_dockerfile = os.path.join(base_dir, "Dockerfile.base")

    # Copy local common package sources into build context
    copy_common_sources(cfg, project_root, base_dir)

    renderer.render_base(
        out_path=base_dockerfile,
        ros_distro=cfg.ros_distro,
        ubuntu=ubuntu,
        common_pkgs=cfg.common_packages,
        workspace_dir=cfg.workspace_dir,
        apt_packages=cfg.apt_packages,
        apt_mirror=cfg.apt_mirror,
        ros_apt_mirror=cfg.ros_apt_mirror,
        base_image_override=cfg.base_image_override,
        enable_apt_caching=cfg.enable_apt_caching,
    )

    base_tag = f"{cfg.registry}/{cfg.image_prefix}_base:{cfg.ros_distro}-{cfg.tag}"

    # Check if we can skip rebuild
    if not force:
        current_hash = compute_base_hash(cfg, project_root)
        cached_hash = load_base_hash(base_dir)

        if current_hash == cached_hash:
            # Check if image exists locally
            try:
                docker.client.image.inspect(base_tag)
                print(f"[prepare_base] Base image {base_tag} is up to date (cached)")
                print(f"[prepare_base] Use 'stage --force-base' to rebuild")
                return
            except Exception:
                print(f"[prepare_base] Base config unchanged but image not found locally, rebuilding...")
        else:
            print(f"[prepare_base] Base configuration changed, rebuilding...")

    # Group hosts by architecture and determine build strategy
    host_arch = get_host_arch()
    hosts_by_arch = {}
    for host in cfg.hosts:
        if host.arch not in hosts_by_arch:
            hosts_by_arch[host.arch] = []
        hosts_by_arch[host.arch].append(host)

    # Separate architectures into local build vs on-device build
    local_build_platforms = []
    on_device_builds = []  # List of (arch, host) tuples

    for arch, hosts in hosts_by_arch.items():
        # Find a host with build_on_device=true for this arch (prefer non-localhost)
        build_host = None
        for h in hosts:
            if h.build_on_device and not is_localhost(h):
                build_host = h
                break

        if build_host:
            on_device_builds.append((arch, build_host))
        else:
            local_build_platforms.append(f"linux/{arch}")

    # Build locally for architectures without build_on_device hosts
    if local_build_platforms:
        print(f"[prepare_base] Building base image {base_tag} locally for: {', '.join(local_build_platforms)}")
        docker.build_multiarch(
            image_tag=base_tag,
            context=base_dir,
            dockerfile=base_dockerfile,
            platforms=local_build_platforms,
            push=True
        )

    # Build on-device for architectures with build_on_device hosts
    for arch, host in on_device_builds:
        print(f"[prepare_base] Building base image {base_tag} on device {host.name} ({arch})")
        docker.build_on_remote_host(
            host=host,
            image_tag=base_tag,
            context=base_dir,
            dockerfile=base_dockerfile,
            push=False
        )

    # Save hash after successful build
    current_hash = compute_base_hash(cfg, project_root)
    save_base_hash(base_dir, current_hash)
    print(Fore.GREEN + f"[prepare_base] Base image built and cached")
