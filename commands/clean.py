#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
from core.config import Config
from core.docker import DockerHelper

def clean_main(project_root: str, remote: bool = False, local: bool = True, config_file: str = 'config.yaml'):
    """
    Clean build artifacts and managed workspaces.

    Args:
        project_root: Path to the project root
        remote: Clean remote hosts as well
        local: Clean local artifacts (default True)
        config_file: Name or path to configuration file (default: 'config.yaml')
    """
    project_root = os.path.abspath(project_root)
    cfg = Config.load(project_root, config_file=config_file)
    docker = DockerHelper()

    # Clean local .forge directory
    if local:
        forge_dir = os.path.join(project_root, ".forge")
        if os.path.exists(forge_dir):
            print(f"[clean] Removing local {forge_dir}")
            shutil.rmtree(forge_dir)
            print(f"[clean] ✓ Removed local .forge")
        else:
            print(f"[clean] Local .forge directory not found, skipping")

        # Clean local component images (but not base image)
        print(f"[clean] Removing local component images...")
        for comp in cfg.components:
            img_tag = comp.image_tag(cfg)
            try:
                docker.client.image.remove(img_tag, force=True)
                print(f"[clean] ✓ Removed local image: {img_tag}")
            except Exception as e:
                print(f"[clean] Image {img_tag} not found locally, skipping")

    if remote:
        # Clean remote hosts
        for host in cfg.hosts:
            mount_root = host.effective_mount_root
            is_localhost = host.ip in ('localhost', '127.0.0.1', '::1')

            if is_localhost:
                print(f"[clean:{host.name}] Skipping remote clean for localhost")
                continue

            print(f"[clean:{host.name}] Cleaning remote directories...")

            # Stop and remove containers first
            try:
                compose_file = os.path.join(project_root, f"docker-compose.{host.name}.yaml")
                if os.path.exists(compose_file):
                    print(f"[clean:{host.name}] Stopping containers...")
                    subprocess.run(
                        ["ssh", f"{host.user}@{host.ip}",
                         f"cd {mount_root} && docker compose -f docker-compose.{host.name}.yaml down 2>/dev/null || true"],
                        check=False
                    )
            except Exception as e:
                print(f"[clean:{host.name}] Warning: Failed to stop containers: {e}")

            # Clean component images on remote host (but not base image)
            print(f"[clean:{host.name}] Removing component images on remote host...")
            host_components = [c for c in cfg.components if c.runs_on == host.name]
            for comp in host_components:
                img_tag = comp.image_tag(cfg)
                try:
                    subprocess.run(
                        ["ssh", f"{host.user}@{host.ip}",
                         f"docker image rm -f {img_tag} 2>/dev/null || true"],
                        check=False
                    )
                    print(f"[clean:{host.name}] ✓ Removed image: {img_tag}")
                except Exception as e:
                    print(f"[clean:{host.name}] Warning: Failed to remove {img_tag}: {e}")

            # Determine remote project path (assuming same relative structure)
            remote_forge = f"~/{os.path.basename(project_root)}/.forge"

            # Remove both mount_root and .forge directories
            try:
                cmd = ["ssh", f"{host.user}@{host.ip}", f"rm -rf {mount_root} {remote_forge}"]
                print(f"[clean:{host.name}] Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                print(f"[clean:{host.name}] ✓ Removed {mount_root} and {remote_forge}")
            except subprocess.CalledProcessError as e:
                print(f"[clean:{host.name}] ERROR: Failed to clean remote: {e}")

    print("[clean] Done")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean build artifacts and workspaces")
    parser.add_argument("-p", "--project-root", default=".", help="Path to project root")
    parser.add_argument("-r", "--remote", action="store_true", help="Clean remote hosts")
    parser.add_argument("--local-only", action="store_true", help="Clean only local artifacts")

    args = parser.parse_args()

    local = not args.remote or not args.local_only
    remote = args.remote

    clean_main(args.project_root, remote=remote, local=local)
