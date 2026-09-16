#!/usr/bin/env python3
import os
import sys
import getpass
import yaml
from colorama import Fore

def init_main(project_root: str, config_file: str = 'config.yaml'):
    # 1) Prep root
    root = os.path.abspath(project_root)
    os.makedirs(root, exist_ok=True)
    os.chdir(root)

    if os.path.exists(config_file):
        print(Fore.RED + f"[init] {config_file} already exists, aborting.", file=sys.stderr)
        sys.exit(1)

    print(Fore.CYAN + "Welcome to forge! Let's set up your project…")

    # 2) Minimal prompts
    distro = input("ROS distro [humble]: ").strip() or "humble"
    domain = input("ROS domain ID [0]: ").strip() or "0"
    registry = input("Docker registry [docker.io/username]: ").strip() or "docker.io/username"
    prefix   = input("Image prefix [myrobot]: ").strip() or "myrobot"

    # 3) Hosts block
    num_hosts = input("Number of target hosts [1]: ").strip() or "1"
    try:
        count = int(num_hosts)
    except ValueError:
        count = 1

    hosts = []
    for i in range(count):
        print(f"Host #{i+1}:")
        name = input("  name: ").strip()
        ip   = input("  ip/address: ").strip()
        user = input(f"  ssh user [{getpass.getuser()}]: ").strip() or getpass.getuser()
        arch = input("  architecture [amd64]: ").strip() or "amd64"
        hosts.append({
            "name": name,
            "ip":   ip,
            "user": user,
            "arch": arch
        })

    # 4) Build the dict and dump to YAML
    cfg = {
        "ros_distro": distro,
        "ros_domain_id": int(domain),
        "registry": registry,
        "image_prefix": prefix,
        "hosts": hosts,
        # placeholders: user will fill these in below
        "common_packages": [],
        "components": []
    }

    with open(config_file, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
        # now append commented placeholders and usage hints
        f.write("\n")
        f.write("# ─── Shared/Common Packages ─────────────────────────────────────\n")
        f.write("# common_packages:\n")
        f.write("#   - name: my_msgs\n")
        f.write("#     folder: common_packages/my_msgs\n")
        f.write("#     repo: https://github.com/you/my_msgs.git\n")
        f.write("#     branch: main\n\n")
        f.write("# ─── Components ────────────────────────────────────────────────\n")
        f.write("# components:\n")
        f.write("#   # Single source component\n")
        f.write("#   - name: navigation\n")
        f.write("#     source: packages/navigation_stack\n")
        f.write("#     runs_on: main_computer\n")
        f.write("#     entrypoint: ros2 launch nav2_bringup navigation_launch.py\n")
        f.write("#     devices: []\n")
        f.write("#     ports: []\n\n")
        f.write("#   # Multi-source component\n")
        f.write("#   - name: perception_system\n")
        f.write("#     sources:\n")
        f.write("#       - packages/camera_driver\n")
        f.write("#       - packages/lidar_driver\n")
        f.write("#       - shared/sensor_msgs\n")
        f.write("#     runs_on: perception_unit\n")
        f.write("#     entrypoint: ros2 launch perception_fusion main.launch.py\n")
        f.write("#     devices:\n")
        f.write("#       - \"/dev/video0:/dev/video0\"\n\n")
        f.write("#   # VCS repository component\n")
        f.write("#   - name: micro_ros_agent\n")
        f.write("#     repositories:\n")
        f.write("#       - url: https://github.com/micro-ROS/micro_ros_setup\n")
        f.write("#         version: humble\n")
        f.write("#         folder: micro_ros_setup\n")
        f.write("#     runs_on: gateway\n")
        f.write("#     entrypoint: ros2 run micro_ros_agent micro_ros_agent\n\n")
        f.write("# ─── Next Steps ───────────────────────────────────────────────\n")
        f.write("# 1) Create your ROS packages in logical directories (e.g., packages/)\n")
        f.write("# 2) Populate common_packages/ with any shared packages\n")
        f.write("# 3) Edit the components above to reference your packages\n")
        f.write("# 4) Run `forge stage` to generate Dockerfiles & compose\n")
        f.write("# 5) Run `forge build` to compile in Docker\n")
        f.write("# 6) Run `forge deploy` to sync and launch containers\n\n")
        f.write("# ─── Workspace Structure ─────────────────────────────────────────\n")
        f.write("# Your project directory can be organized however you like:\n")
        f.write("# my_robot_project/\n")
        f.write("# ├── config.yaml           # This file\n")
        f.write("# ├── packages/             # Your ROS packages\n")
        f.write("# │   ├── navigation_stack/\n")
        f.write("# │   └── camera_driver/\n")
        f.write("# ├── shared/               # Shared packages\n")
        f.write("# │   └── sensor_msgs/\n")
        f.write("# └── .forge/               # Managed by forge\n")
        f.write("#     └── workspaces/       # Component workspaces (auto-generated)\n\n")

    # 5) Scaffold on-disk dirs (only create managed directory)
    os.makedirs(".forge", exist_ok=True)

    # Create .gitignore for managed directory
    gitignore_path = os.path.join(".forge", ".gitignore")
    with open(gitignore_path, "w") as f:
        f.write("# forge managed files\n")
        f.write("workspaces/\n")
        f.write("cache/\n")
        f.write("repos/\n")

    print(Fore.GREEN + f"[init] Scaffold complete; see {config_file} for placeholders.")
