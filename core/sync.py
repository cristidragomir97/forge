# core/sync.py
import os
import subprocess

def rsync_file(local_path: str, host, remote_path: str):
    # Check if host is localhost
    is_localhost = host.ip in ('localhost', '127.0.0.1', '::1')

    if is_localhost:
        # For localhost, use local rsync without SSH
        # Ensure the destination directory exists
        os.makedirs(os.path.dirname(remote_path), exist_ok=True)
        cmd = [
            "rsync", "-az", "--inplace", "--no-whole-file",
            local_path,
            remote_path
        ]
        print(f"[deploy] rsync (localhost): {' '.join(cmd)}")
    else:
        cmd = [
            "rsync", "-az", "--inplace", "--no-whole-file",
            local_path,
            f"{host.user}@{host.ip}:{remote_path}"
        ]
        print(f"[deploy] rsync: {' '.join(cmd)}")

    subprocess.run(cmd, check=True)

class SyncManager:
    def __init__(self, cfg):
        self.build = os.path.join(cfg.root, cfg.build_dir)
        self.workspace_dir = cfg.workspace_dir


    def rsync_builds(self, project_root,  host, components):
        mount_root = host.effective_mount_root

        # Check if host is localhost
        is_localhost = host.ip in ('localhost', '127.0.0.1', '::1')

        for comp in components:
            src = os.path.join(self.build, comp.name, self.workspace_dir) + "/"
            if not os.path.isdir(src):
                print(f"[sync] Skipping {comp.name} (no build found at {src})")
                continue

            if is_localhost:
                # For localhost, builds are already in place - no sync needed
                # The compose file will mount directly from .forge/build/<component>/ros_ws
                print(f"[sync] Skipping rsync for {comp.name} on localhost ({host.name})")
                print(f"[sync] Using local build directory: {src}")
                continue
            else:
                print(f"[sync] Syncing {comp.name} build to {host.name} ({host.ip})")
                dst = f"{host.user}@{host.ip}:{mount_root}/{comp.name}/{self.workspace_dir}/"

                # Create directory and ensure proper ownership
                remote_dir = f"{mount_root}/{comp.name}/{self.workspace_dir}"
                setup_cmd = [
                    "ssh", f"{host.user}@{host.ip}",
                    f"mkdir -p {remote_dir} && chown -R {host.user}:{host.user} {mount_root}"
                ]
                print(f"[sync] Setting up remote directory: {remote_dir}")
                subprocess.run(setup_cmd, check=True)

                cmd = [
                    "rsync", "-az", "--inplace", "--no-whole-file", "--delete",
                    "-e", "ssh", src, dst
                ]
                print(f"[sync] {host.name}: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
