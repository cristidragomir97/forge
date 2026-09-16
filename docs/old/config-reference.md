# Configuration File Reference

This document provides a comprehensive reference for writing `config.yaml` files for forge. The configuration file is the central place where you define your robot system's structure, components, deployment targets, and behavior.

## Overview

The `config.yaml` file is a YAML document that describes:
- ROS environment settings
- Docker registry and image configuration
- Target deployment hosts
- System-wide packages and dependencies
- Individual components and their requirements
- Optional features like DDS routing and caching

## File Structure

```yaml
# Required fields
ros_distro: <string>
ros_domain_id: <integer>
registry: <string>
image_prefix: <string>

# Optional global settings
enable_apt_caching: <boolean>
deploy_mode: <string>
build_dir: <string>
components_dir: <string>
compose_file: <string>
mount_root: <string>
docker_port: <integer>
tag: <string>
enable_dds_router: <boolean>
discovery_server: <string>

# System packages
apt_packages: <list>

# Shared dependencies
common_packages: <list>

# Application components
components: <list>

# Deployment targets
hosts: <list>
```

## Required Fields

### `ros_distro`
**Type:** `string`
**Description:** The ROS 2 distribution to use (e.g., `humble`, `iron`, `jazzy`)
**Example:** `ros_distro: humble`

### `ros_domain_id`
**Type:** `integer`
**Description:** ROS Domain ID for DDS isolation between robot systems
**Range:** 0-232
**Example:** `ros_domain_id: 0`

### `registry`
**Type:** `string`
**Description:** Docker registry URL where images will be stored and pulled from
**Example:** `registry: docker.io/username`

### `image_prefix`
**Type:** `string`
**Description:** Prefix for all generated Docker image names
**Example:** `image_prefix: myrobot`

## Optional Global Settings

### `enable_apt_caching`
**Type:** `boolean`
**Default:** `false`
**Description:** Enable apt package caching to speed up container builds
**Example:** `enable_apt_caching: true`

### `deploy_mode`
**Type:** `string`
**Default:** `image`
**Description:** Deployment strategy (currently only `image` is supported)
**Example:** `deploy_mode: image`

### `build_dir`
**Type:** `string`
**Default:** `build`
**Description:** Directory for build artifacts and generated files
**Example:** `build_dir: build`

### `components_dir`
**Type:** `string`
**Default:** `components`
**Description:** Directory containing component source code
**Example:** `components_dir: components`

### `compose_file`
**Type:** `string`
**Default:** `docker-compose.yml`
**Description:** Base name for generated Docker Compose files
**Example:** `compose_file: docker-compose.yml`

### `mount_root`
**Type:** `string`
**Default:** `/home/{current_user}/ros_builds`
**Description:** Root directory on target hosts for mounting ROS workspaces
**Example:** `mount_root: /opt/robot/workspaces`

### `docker_port`
**Type:** `integer`
**Default:** `2375`
**Description:** Docker daemon port on target hosts
**Example:** `docker_port: 2376`

### `tag`
**Type:** `string`
**Default:** `latest`
**Description:** Docker image tag for all generated images
**Example:** `tag: v1.2.3`

### `enable_dds_router`
**Type:** `boolean`
**Default:** `false`
**Description:** Enable DDS Router for multi-host communication
**Example:** `enable_dds_router: true`

### `discovery_server`
**Type:** `string`
**Default:** `localhost`
**Description:** DDS Discovery Server address
**Example:** `discovery_server: 192.168.1.100`

## System Packages

### `apt_packages`
**Type:** `list of strings`
**Default:** `[]`
**Description:** System-level apt packages to install in the base image
**Example:**
```yaml
apt_packages:
  - htop
  - vim
  - tmux
```

## Common Packages

### `common_packages`
**Type:** `list of objects`
**Default:** `[]`
**Description:** Shared ROS packages available to all components, installed in the base image

**Structure:**
```yaml
common_packages:
  - name: <string>          # Package name
    folder: <string>        # Local folder path
    repo: <string>          # Git repository URL (optional)
    branch: <string>        # Git branch (optional)
```

**Example:**
```yaml
common_packages:
  - name: my_msgs
    folder: common_packages/my_msgs
    repo: https://github.com/myorg/my_msgs.git
    branch: main
```

## Components

### `components`
**Type:** `list of objects`
**Default:** `[]`
**Description:** Individual ROS components that make up your robot system

**Structure:**
```yaml
components:
  - name: <string>                    # Required: Component identifier
    sources: <list of strings>        # Optional: Multiple source paths
    source: <string>                  # Optional: Single source path
    folder: <string>                  # Deprecated: Use source/sources instead
    entrypoint: <string>              # Optional: Container startup command
    launch_args: <string>             # Optional: Arguments for entrypoint
    devices: <list of strings>        # Optional: Device mappings
    ports: <list of strings>          # Optional: Port mappings
    environment: <object>             # Optional: Custom environment variables
    preinstall: <list of strings>     # Optional: Commands before build
    postinstall: <list of strings>    # Optional: Commands after build
    runs_on: <string>                 # Optional: Target host name
    repositories: <list of objects>   # Optional: VCS dependencies
    apt_packages: <list of strings>   # Optional: Component-specific packages
    simulate: <boolean>               # Optional: Simulation flag
    image: <string>                   # Optional: Pre-built base image
```

### Component Fields

#### `name` (required)
**Type:** `string`
**Description:** Unique identifier for the component
**Example:** `name: navigation`

#### `sources`
**Type:** `list of strings`
**Description:** Paths to ROS packages or workspaces that make up this component. Each path can point to a single ROS package (containing package.xml) or a workspace src directory containing multiple packages.
**Example:**
```yaml
sources:
  - packages/navigation_stack
  - packages/local_planner
  - shared/nav_msgs
```

#### `source`
**Type:** `string`
**Description:** Single source path for components with only one package. Alternative to `sources` for simpler cases.
**Example:** `source: packages/camera_driver`

#### `folder` (deprecated)
**Type:** `string`
**Description:** Legacy field for backward compatibility. Use `source` or `sources` instead.
**Example:** `folder: components/navigation`

#### `entrypoint`
**Type:** `string`
**Description:** Command to run when the container starts
**Example:** `entrypoint: ros2 launch nav2_bringup navigation_launch.py`

#### `launch_args`
**Type:** `string`
**Description:** Additional arguments for the entrypoint command
**Example:** `launch_args: use_sim_time:=true`

#### `devices`
**Type:** `list of strings`
**Description:** Device mappings in format `host_device:container_device`
**Example:**
```yaml
devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"
  - "/dev/video0:/dev/video0"
```

#### `ports`
**Type:** `list of strings`
**Description:** Port mappings in format `host_port:container_port`
**Example:**
```yaml
ports:
  - "8080:8080"
  - "1234:1234/udp"
```

#### `environment`
**Type:** `object (key-value pairs)`
**Description:** Custom environment variables to set in the container
**Note:** ROS_DOMAIN_ID, ROS_DISTRO, and ROS_DISCOVERY_SERVER are set automatically
**Example:**
```yaml
environment:
  MY_CUSTOM_VAR: "value"
  SENSOR_RATE_HZ: "50"
  DEBUG_MODE: "true"
```

#### `preinstall`
**Type:** `list of strings`
**Description:** Commands to run before building the ROS workspace
**Example:**
```yaml
preinstall:
  - "apt-get update"
  - "pip install -r requirements.txt"
```

#### `postinstall`
**Type:** `list of strings`
**Description:** Commands to run after building the ROS workspace
**Example:**
```yaml
postinstall:
  - "ros2 run micro_ros_setup create_agent_ws.sh"
  - "ros2 run micro_ros_setup build_agent.sh"
```

#### `runs_on`
**Type:** `string`
**Description:** Name of the host where this component should be deployed
**Example:** `runs_on: robot_base`

#### `repositories`
**Type:** `list of objects`
**Description:** VCS repositories to include in the component's workspace

**Repository Structure:**
```yaml
repositories:
  - url: <string>       # Git repository URL
    version: <string>   # Branch, tag, or commit
    folder: <string>    # Destination folder in workspace
```

**Example:**
```yaml
repositories:
  - url: https://github.com/micro-ROS/micro_ros_setup
    version: humble
    folder: micro_ros_agent
  - url: https://github.com/myorg/custom_driver.git
    version: v2.1.0
    folder: drivers/custom_driver
```

#### `apt_packages`
**Type:** `list of strings`
**Description:** Apt packages specific to this component
**Example:**
```yaml
apt_packages:
  - libopencv-dev
  - libeigen3-dev
```

#### `simulate`
**Type:** `boolean`
**Default:** `false`
**Description:** Flag indicating if this is a simulation component
**Example:** `simulate: true`

#### `image`
**Type:** `string`
**Description:** Pre-built Docker image to use instead of building from source
**Note:** When using a pre-built image, `folder`, `apt_packages`, and `repositories` should not be specified
**Example:** `image: osrf/ros:humble-desktop`

## Hosts

### `hosts`
**Type:** `list of objects` or `object`
**Description:** Target machines for deployment. Can be a single host object or list of hosts

**Structure:**
```yaml
hosts:
  - name: <string>      # Required: Host identifier
    ip: <string>        # Required: IP address or hostname
    user: <string>      # Required: SSH username
    arch: <string>      # Required: Target architecture
    port: <integer>     # Optional: Docker daemon port
    manager: <boolean>  # Optional: DDS manager flag
```

### Host Fields

#### `name` (required)
**Type:** `string`
**Description:** Unique identifier for the host
**Example:** `name: robot_base`

#### `ip` (required)
**Type:** `string`
**Description:** IP address or hostname for SSH connections
**Example:** `ip: 192.168.1.100` or `ip: robot.local`

#### `user` (required)
**Type:** `string`
**Description:** SSH username for connecting to the host
**Example:** `user: ubuntu`

#### `arch` (required)
**Type:** `string`
**Description:** Target architecture for cross-compilation
**Valid values:** `amd64`, `arm64`, `armv7`
**Example:** `arch: arm64`

#### `port`
**Type:** `integer`
**Default:** `2375`
**Description:** Docker daemon port on this specific host
**Example:** `port: 2376`

#### `manager`
**Type:** `boolean`
**Default:** `false`
**Description:** Whether this host acts as a DDS manager
**Example:** `manager: true`

## Complete Example

```yaml
# Basic settings
ros_distro: humble
ros_domain_id: 42
registry: docker.io/mycompany
image_prefix: autonomous_robot

# Optional settings
enable_apt_caching: true
enable_dds_router: true
discovery_server: 192.168.1.100
tag: v2.0.0

# System packages
apt_packages:
  - htop
  - vim
  - can-utils

# Shared packages
common_packages:
  - name: robot_msgs
    folder: common_packages/robot_msgs
    repo: https://github.com/mycompany/robot_msgs.git
    branch: main

# Components
components:
  # Multi-package perception component
  - name: perception_system
    sources:
      - packages/camera_driver
      - packages/lidar_processor
      - packages/perception_fusion
      - shared/sensor_msgs
    runs_on: jetson_xavier
    entrypoint: ros2 launch perception_fusion main.launch.py
    devices:
      - "/dev/video0:/dev/video0"
      - "/dev/ttyUSB0:/dev/ttyUSB0"
    apt_packages:
      - libopencv-dev
      - librealsense2-dev

  # Single-package control component
  - name: control
    source: packages/robot_control
    runs_on: control_unit
    entrypoint: ros2 launch robot_control control.launch.py
    devices:
      - "/dev/ttyACM0:/dev/ttyACM0"
    environment:
      CONTROL_RATE_HZ: "100"
      SERVO_PORT: "/dev/ttyACM0"
    preinstall:
      - "pip install pyserial"

  # VCS repository component
  - name: micro_ros_agent
    repositories:
      - url: https://github.com/micro-ROS/micro_ros_setup
        version: humble
        folder: micro_ros_setup
    runs_on: gateway
    entrypoint: ros2 run micro_ros_agent micro_ros_agent
    devices:
      - "/dev/ttyUSB1:/dev/ttyUSB1"

  # Simulation component with pre-built image
  - name: gazebo_sim
    simulate: true
    image: osrf/ros:humble-desktop
    entrypoint: ros2 launch robot_gazebo simulation.launch.py
    ports:
      - "11345:11345"

# Deployment hosts
hosts:
  - name: jetson_xavier
    ip: 192.168.1.101
    user: nvidia
    arch: arm64
    manager: true

  - name: control_unit
    ip: 192.168.1.102
    user: robot
    arch: amd64

  - name: gateway
    ip: 192.168.1.103
    user: ubuntu
    arch: amd64
```

## Workspace Structure

With the new design, your project directory structure becomes more flexible:

```
my_robot_project/
├── config.yaml                    # Main configuration
├── packages/                      # Your ROS packages (organized as you like)
│   ├── camera_driver/
│   │   ├── package.xml
│   │   └── src/
│   ├── lidar_processor/
│   │   ├── package.xml
│   │   └── src/
│   ├── perception_fusion/
│   │   ├── package.xml
│   │   └── src/
│   └── robot_control/
│       ├── package.xml
│       └── src/
├── shared/                        # Shared packages
│   └── sensor_msgs/
│       ├── package.xml
│       └── msg/
├── common_packages/               # Common packages for base image
│   └── robot_msgs/
├── build/                         # Build artifacts (auto-generated)
└── .forge/                 # Managed by forge (auto-generated)
    └── workspaces/
        ├── perception_system/     # Component workspace with symlinked sources
        │   └── src/
        │       ├── camera_driver -> ../../../packages/camera_driver/
        │       ├── lidar_processor -> ../../../packages/lidar_processor/
        │       ├── perception_fusion -> ../../../packages/perception_fusion/
        │       └── sensor_msgs -> ../../../shared/sensor_msgs/
        └── control/
            └── src/
                └── robot_control -> ../../../packages/robot_control/
```

## Validation Rules

1. **Required fields** must be present: `ros_distro`, `ros_domain_id`, `registry`, `image_prefix`
2. **Component names** must be unique across all components
3. **Host names** must be unique across all hosts
4. **Components with `image` field** cannot have `source`, `sources`, `folder`, `apt_packages`, or `repositories`
5. **Components must have either** `source`, `sources`, `repositories`, or `image` - at least one source of packages
6. **Host references** in `runs_on` must match defined host names
7. **Device and port mappings** must follow the `host:container` format
8. **Architecture values** must be valid Docker platform names
9. **Source paths** must point to existing directories containing ROS packages

## Migration from Legacy Format

If you have existing projects using the old `folder` field:

1. **Components will continue to work** with deprecation warnings
2. **Migrate gradually** by replacing `folder: components/name` with `source: components/name/ros_ws/src`
3. **Take advantage of flexibility** by reorganizing packages and using `sources` for multi-package components
4. **Update workflows** to place packages in logical directories rather than the rigid `components/name/ros_ws/src` structure

## Best Practices

1. **Use descriptive names** for components and hosts
2. **Group related functionality** into single components using `sources`
3. **Organize packages logically** in directories like `packages/`, `drivers/`, `algorithms/`
4. **Use single `source`** for simple one-package components
5. **Use `sources` array** for complex multi-package components
6. **Minimize apt packages** in favor of ROS dependencies when possible
7. **Use version pinning** for repositories in production
8. **Test configurations** with simulation components first
9. **Document custom fields** with YAML comments
10. **Version control** your config.yaml alongside your code
11. **Keep source code separate** from forge managed files