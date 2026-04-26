#!/usr/bin/env python3
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from colorama import Fore
from core.config import Config
from core.docker import DockerHelper, is_localhost
from core.models import Host
from python_on_whales.exceptions import DockerException
from utils.timing import timed


def sync_main(project_root: str,
              host_name: Optional[str] = None,
              component: Optional[str] = None,
              skip_base: bool = False,
              skip_components: bool = False,
              jobs: int = 1,
              config_file: str = 'config.yaml'):
    """
    Pull images on remote hosts so they're ready to launch.

    By default pulls the base image and every component image on each host.
    Hosts that build on-device are skipped (their images are already local).
    """
    with timed("sync"):
        _sync_main_impl(project_root, host_name, component, skip_base, skip_components, jobs, config_file)


def _sync_main_impl(project_root: str,
                    host_name: Optional[str],
                    component: Optional[str],
                    skip_base: bool,
                    skip_components: bool,
                    jobs: int,
                    config_file: str):
    project_root = os.path.abspath(project_root)
    os.chdir(project_root)

    cfg = Config.load(project_root, config_file=config_file)
    docker = DockerHelper()

    hosts = cfg.hosts
    if host_name:
        host = next((h for h in hosts if h.name == host_name), None)
        if not host:
            sys.exit(f"[sync] ERROR: Host '{host_name}' not found in config.")
        hosts = [host]

    base_tag = cfg.base_image

    pulls = []  # list of (host, image, label)
    for host in hosts:
        if host.build_on_device and not is_localhost(host):
            print(f"[sync] Skipping '{host.name}' (build_on_device: images are local)")
            continue

        host_components = [c for c in cfg.components if c.runs_on == host.name]
        if component:
            host_components = [c for c in host_components if c.name == component]

        if not skip_base:
            pulls.append((host, base_tag, "base"))

        if not skip_components:
            for comp in host_components:
                pulls.append((host, comp.image_tag(cfg), comp.name))

    if not pulls:
        print("[sync] Nothing to pull.")
        return

    def _pull(host: Host, image: str, label: str):
        print(f"[sync:{host.name}] Pulling {label} ({image})...")
        try:
            docker.pull_image_on_host(host, image)
        except DockerException:
            print(Fore.RED + f"[sync:{host.name}] Failed to pull {image} on '{host.name}' ({host.ip})", file=sys.stderr)
            raise
        print(Fore.GREEN + f"[sync:{host.name}] ✓ {label}")

    max_workers = max(1, min(jobs, len(pulls)))
    if max_workers > 1:
        print(f"[sync] Pulling {len(pulls)} image(s) in parallel (jobs={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_pull, h, img, lbl): (h, img, lbl) for h, img, lbl in pulls}
            first_error: Optional[BaseException] = None
            for future in as_completed(futures):
                try:
                    future.result()
                except BaseException as e:
                    if first_error is None:
                        first_error = e
            if first_error is not None:
                raise first_error
    else:
        for host, image, label in pulls:
            _pull(host, image, label)

    print(Fore.GREEN + f"[sync] Done.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--project-root", default=".", help="Path to project root")
    parser.add_argument("--host", default=None, help="Only pull on this host (name from config)")
    parser.add_argument("-c", "--component", default=None, help="Only pull this component image")
    parser.add_argument("--skip-base", action="store_true", help="Skip pulling the base image")
    parser.add_argument("--skip-components", action="store_true", help="Skip pulling component images")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="Max parallel pulls")
    args = parser.parse_args()
    sync_main(args.project_root, args.host, args.component,
              args.skip_base, args.skip_components, args.jobs)
