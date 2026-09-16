# Configuration

All of your robot's components, hosts, deployment logic, and ROS metadata are defined in one centralized YAML file. This file is declarative, version-controllable, and reproducible.

## Global Configuration

```yaml
# Required fields
ros_distro: humble                    # ROS 2 distribution (humble, iron, jazzy)
ros_domain_id: 0                      # ROS domain ID (0-232)
registry: docker.io/myuser            # Docker registry URL
image_prefix: myrobot                 # Docker image name prefix

# Optional fields
deploy_mode: image                    # "image" (registry push/pull, default) or "transfer" (docker save/load, no registry)
tag: latest                           # Docker image tag (default: latest)
build_dir: .forge/build               # Build output directory
workspace_dir: ros_ws                 # ROS workspace directory name
mount_root: /home/user/ros_builds     # Remote mount root for builds

# Apt mirrors (for faster builds in certain regions)
apt_mirror: http://mirrors.example.com/ubuntu           # Custom Ubuntu apt mirror
ros_apt_mirror: http://mirrors.example.com/ros2/ubuntu  # Custom ROS apt mirror

# Global apt packages (installed in base image)
apt_packages:
  - vim
  - htop

# ROS Middleware (RMW) configuration
rmw_implementation: fastdds           # Options: "fastdds" (default) or "zenoh"

# FastDDS-specific (used when rmw_implementation: fastdds)
enable_dds_router: false              # Enable DDS router container
discovery_server: localhost           # Discovery server address

# Zenoh-specific (used when rmw_implementation: zenoh)
zenoh:
  router_image: eclipse-zenoh/zenoh:latest  # Zenoh router Docker image
  router_port: 7447                         # Zenoh router port
```

### Required Fields

| Field | Description |
|-------|-------------|
| `ros_distro` | ROS 2 distribution (humble, iron, jazzy) |
| `ros_domain_id` | Domain ID for DDS isolation (0-232) |
| `registry` | Docker registry URL |
| `image_prefix` | Prefix for generated image names |

### Optional Fields

| Field | Default | Description |
|-------|---------|-------------|
| `deploy_mode` | `image` | `image` pushes to `registry` and pulls on each host; `transfer` does `docker save` locally and `docker load` directly onto each host's Docker API (`host.port`), skipping the registry entirely |
| `tag` | `latest` | Docker image tag |
| `build_dir` | `.forge/build` | Local build output directory |
| `workspace_dir` | `ros_ws` | ROS workspace name |
| `mount_root` | `/home/$USER/ros_builds` | Remote directory for build artifacts |
| `apt_mirror` | *(none)* | Custom Ubuntu apt mirror URL |
| `ros_apt_mirror` | *(none)* | Custom ROS apt mirror URL |
| `apt_packages` | `[]` | System packages to install in base image |
| `rmw_implementation` | `fastdds` | ROS middleware (`fastdds` or `zenoh`) |
| `enable_dds_router` | `false` | Enable DDS router container (FastDDS only) |
| `discovery_server` | `localhost` | DDS discovery server address (FastDDS only) |
| `zenoh` | *(see above)* | Zenoh configuration block |

---

## Hosts

Define the machines in your system.

```yaml
hosts:
  - name: rpi5
    ip: pi5.local
    user: user
    arch: arm64
    port: 2375                        # Docker daemon port (default: 2375)
    manager: true                     # DDS discovery server manager role
    dds_ip: 192.168.1.100            # Secondary IP for DDS (defaults to ip)
    mount_root: /home/user/builds    # Override global mount_root for this host
    build_on_device: true            # Build on device (faster than emulation)
```

### Host Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier for this host |
| `ip` | Yes | Hostname or IP address for deployment |
| `user` | Yes | SSH username for rsync and remote actions |
| `arch` | Yes | Target architecture (amd64, arm64, armv7) |
| `port` | No | Docker daemon TCP port (default: 2375) |
| `manager` | No | Set to `true` to designate this host as the middleware router |
| `dds_ip` | No | Alternative IP for DDS/Zenoh communication (useful for multi-NIC setups) |
| `mount_root` | No | Per-host override for build artifact directory |
| `build_on_device` | No | Build base images, component images, and workspaces natively on this device instead of using slow QEMU emulation locally (much faster for ARM64 targets) |

---

## Common Packages

Define packages or libraries that should be available in all components. You can use either VCS-based repositories or local source folders.

```yaml
common_packages:
  # VCS-based package (one or more repositories)
  - name: my_msgs
    repositories:
      - url: https://github.com/you/my_msgs.git
        version: main
        # folder is optional - auto-derived from URL if not specified
      - url: https://github.com/you/my_msgs_extras.git
        version: develop

  # Local source package (one or more folders)
  - name: robot_control
    source:
      - ros_ws/robot_control
      - ros_ws/robot_control_plugin
```

Common packages are included in the base image so they don't get duplicated per component—saving build time and storage.

---

## Components

Components are modular, swappable units of your robot software. Forge supports three ways to define components:

### 1. Forge-Managed Build (Default)

Forge generates a Dockerfile and manages the build process:

```yaml
components:
  - name: micro_ros_agent
    source: components/micro_ros_agent/ros_ws/src
    runs_on: rpi5
    apt_packages: []
    repositories:
      - url: https://github.com/micro-ROS/micro_ros_setup
        version: humble
        folder: micro_ros_agent
    postinstall:
      - "ros2 run micro_ros_setup create_agent_ws.sh"
      - "ros2 run micro_ros_setup build_agent.sh"
    entrypoint: ros2 run micro_ros_agent micro_ros_agent serial
    launch_args: "--dev /dev/ttyUSB0 -v6"
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
```

### 2. External Pre-Built Image

Use existing Docker images from registries without any build:

```yaml
components:
  - name: rosboard
    image: thehale/rosboard:latest
    runs_on: rpi5
    ports:
      - "8888:8888"
    entrypoint: rosboard
```

### 3. Custom Dockerfile Build

Build from your own Dockerfile for full control (GPU drivers, complex builds, etc.):

```yaml
components:
  - name: camera_driver
    build: docker/camera
    runs_on: orin
    devices:
      - "/dev/video0:/dev/video0"
    entrypoint: ros2 launch camera driver.launch.py
```

### Component Fields Reference

#### Source Configuration

| Field | Description |
|-------|-------------|
| `name` | Unique identifier for this component |
| `source` / `sources` | Local source paths for ROS packages |
| `runs_on` | Target host name (required) |

#### Dependencies

| Field | Description |
|-------|-------------|
| `repositories` | VCS repositories in vcstool format |
| `apt_packages` | System packages to install |
| `pip_packages` | Python packages to install |

#### Runtime

| Field | Description |
|-------|-------------|
| `entrypoint` | Container startup command |
| `launch_args` | Arguments for entrypoint |
| `environment` | Environment variables as key-value pairs |

#### Hardware

| Field | Description |
|-------|-------------|
| `devices` | Device mappings (e.g., `/dev/ttyUSB0:/dev/ttyUSB0`) |
| `ports` | Port mappings (e.g., `8080:80`) |

#### Build Hooks

| Field | Description |
|-------|-------------|
| `preinstall` | Commands to run before installing dependencies |
| `postinstall` | Commands to run after installing dependencies |

#### Container Options

| Field | Default | Description |
|-------|---------|-------------|
| `privileged` | `false` | Run in privileged mode |
| `runtime` | *(none)* | Container runtime (e.g., `nvidia`) |
| `nvidia` | `false` | Enable NVIDIA GPU support |
| `gpu_count` | *(none)* | Number of GPUs to allocate |
| `gpu_device_ids` | *(none)* | Specific GPU device IDs |
| `volumes` | `[]` | Additional volume mounts |
| `stdin_open` | `false` | Keep stdin open |
| `tty` | `false` | Allocate pseudo-TTY |

#### Performance

| Field | Description |
|-------|-------------|
| `shm_size` | Shared memory size (e.g., `2g`) |
| `ipc_mode` | IPC mode (e.g., `host`) |
| `cpuset` | CPU pinning (e.g., `0-3`) |

---

## Component Build Behavior

| Type | Build Timing | Notes |
|------|--------------|-------|
| Forge-managed | `build` step | Compilation occurs during the build command |
| External image | None | Image used as-is, no build step |
| Custom Dockerfile | `stage` step | Build happens during stage command |

See [external-images.md](external-images.md) for detailed examples and migration guides.
