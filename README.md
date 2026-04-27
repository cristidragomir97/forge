# forge

**forge** is a lightweight tool designed to simplify how you build, prototype, and deploy ROS 2 systems using containers.

It helps you structure your robot software as modular components, run them across one or more machines, and manage everything from a single configuration file. Whether you're wiring up your first prototype or preparing for deployment, `forge` gives you a consistent workflow that grows with your project.

## What forge helps with

- **Prototyping** quickly on your dev machine while keeping things reproducible
- **Deploying** to real robots without ad hoc scripts and broken dependencies
- **Iterating** on your robot system without rebuilding everything from scratch
- **Building fast** — parallel component builds (`-j N`) and shared BuildKit caches for apt/pip/rosdep, so re-stages are seconds and full cold builds skip redundant downloads
- **Scaling** from a single board to a multi-machine setup
- **Sharing** complete robot recipes, not just isolated components

## Philosophy

- **Deployment shouldn't be an afterthought** — Build with deployment in mind from the start
- **Modular, reusable components** — Your robot is made of logical building blocks in a single YAML config
- **One configuration = one robot** — All hosts, components, and settings in one declarative file
- **Native-speed dev, container-grade consistency** — Docker benefits without losing ROS tooling

---

## Quick Start

```bash
# Install
pip install .

# Create a new project
forge my_robot init

# Edit config.yaml to define your robot...

# Build and deploy
forge my_robot prep      # Create base image
forge my_robot stage     # Prepare component images
forge my_robot build     # Compile workspaces
forge my_robot launch    # Deploy to hosts
```

---

## Documentation

| Topic | Description |
|-------|-------------|
| [Configuration](docs/configuration.md) | Global settings, hosts, common packages, and components |
| [Commands](docs/commands.md) | CLI commands: init, prep, stage, build, launch, pixi |
| [Networking](docs/networking.md) | RMW options (FastDDS, Zenoh), middleware setup |
| [Multi-Host Systems](docs/multi-host.md) | Distributed deployments across multiple machines |
| [Visualization](docs/visualization.md) | VNC, GUI tools, rviz2, and RoboStack/pixi |
| [Platform Notes](docs/platform-notes.md) | macOS, Linux, and WSL specifics |
| [Tips & Troubleshooting](docs/tips.md) | Common patterns and problem solving |

---

## Installation

### Prerequisites

- Python 3.10+
- Docker
- pip

### Install from source

```bash
git clone https://github.com/cristidragomir97/forge.git
cd forge
pip install .
```

For development:
```bash
pip install -e .
```

---

## Example Configuration

```yaml
# config.yaml
ros_distro: humble
ros_domain_id: 0
registry: docker.io/myuser
image_prefix: myrobot

hosts:
  - name: robot
    ip: robot.local
    user: ubuntu
    arch: arm64
    manager: true

common_packages:
  - name: my_msgs
    repositories:
      - url: https://github.com/me/my_msgs.git
        version: main

components:
  - name: perception
    source: components/perception/ros_ws/src
    runs_on: robot
    entrypoint: ros2 launch perception bringup.launch.py

  - name: control
    source: components/control/ros_ws/src
    runs_on: robot
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
    entrypoint: ros2 launch control main.launch.py
```

---

## Workflow Overview

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  prep   │ ──► │  stage  │ ──► │  build  │ ──► │ launch  │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │
     ▼               ▼               ▼               ▼
 Base image    Component       Compile ROS      Deploy to
 with common   images with     workspaces       target hosts
 packages      dependencies
```

**Iterating:** After code changes, just run `build` and `launch` again.

---

## Platform Support

| Platform | Host Networking | GUI | Cross-Compile ARM64 |
|----------|-----------------|-----|---------------------|
| Linux | Full | Full | Slow (QEMU) |
| macOS | No | Limited | Fast (native) |
| WSL | Limited | WSLg | Slow (QEMU) |

See [Platform Notes](docs/platform-notes.md) for details.

---

## Middleware Support

forge supports two ROS 2 middleware implementations:

| Middleware | Default | Best For |
|------------|---------|----------|
| **FastDDS** | Yes | Standard ROS 2 deployments |
| **Zenoh** | No | Lower latency, WAN, constrained devices |

```yaml
# Use Zenoh instead of FastDDS
rmw_implementation: zenoh
```

See [Networking](docs/networking.md) for configuration details.

---

## Contributing

Contributions are welcome! Please open an issue or PR on GitHub.

## License

[MIT License](LICENSE)
