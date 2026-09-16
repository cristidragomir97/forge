# External Images and Custom Dockerfiles

Forge-cli now supports three ways to define component images:

## 1. Forge-Managed Build (Default)

The traditional approach where forge generates a Dockerfile based on your configuration:

```yaml
components:
  - name: motion
    source: ros/src/leremix_control
    repositories:
      - url: https://github.com/ros-controls/ros2_control.git
        version: humble
    apt_packages:
      - ros-humble-controller-manager
    runs_on: pi
    entrypoint: ros2 launch leremix_control motion.launch.py
```

**Use when**: Building custom ROS 2 packages with dependency management.

## 2. External Pre-Built Image

Use an existing Docker image from a registry without any build step:

```yaml
components:
  - name: gazebo
    image: osrf/ros:humble-desktop
    runs_on: workstation
    entrypoint: gazebo
    environment:
      DISPLAY: ":0"
```

**Use when**:
- Using community images (Gazebo, RViz, Nav2, etc.)
- Image is already built and published
- No customization needed

**Restrictions**:
- Cannot specify `repositories`, `apt_packages`, or `pip_packages`
- Image must be accessible from the Docker registry
- Will be tagged as `{registry}/{prefix}_{name}:{tag}` in compose files

## 3. Custom Dockerfile Build

Build from your own Dockerfile for full control:

```yaml
components:
  - name: camera
    build: docker/camera
    runs_on: orin
    entrypoint: ros2 launch camera driver.launch.py
    devices:
      - /dev/video0:/dev/video0
```

**Directory structure**:
```
project_root/
  docker/
    camera/
      Dockerfile       # Required
      custom_script.sh
      driver_config.yaml
```

**Use when**:
- Need GPU drivers (CUDA, TensorRT)
- Complex multi-stage builds
- Custom base images
- Advanced build optimizations

**Restrictions**:
- Cannot specify `repositories`, `apt_packages`, or `pip_packages`
- Must provide a `Dockerfile` in the specified directory
- Build context is the directory containing the Dockerfile

## Configuration Reference

### Fields

- **`image`** (string, optional): External pre-built Docker image
- **`build`** (string, optional): Path to directory containing Dockerfile (relative to project root)
- **`source`/`sources`** (string/list, optional): Local source paths for forge-managed builds

### Mutual Exclusivity

Only one of these can be specified per component:
- `image` (external image)
- `build` (custom Dockerfile)
- `source` or `sources` (forge-managed build)
- `folder` (legacy, deprecated)

When using `image` or `build`, you **cannot** specify:
- `repositories`
- `apt_packages`
- `pip_packages`

These are only for forge-managed builds.

### Shared Fields

All component types support:
- `runs_on`: Target host (required)
- `entrypoint`: Container command
- `launch_args`: Arguments for entrypoint
- `devices`: Device mappings
- `ports`: Port mappings
- `environment`: Environment variables
- `optimisations`: Performance settings (shm, ipc, pinned_cores, etc.)

## Examples

### Example 1: Using Official ROS Image

```yaml
components:
  - name: rviz
    image: osrf/ros:humble-desktop
    runs_on: workstation
    entrypoint: rviz2
    environment:
      DISPLAY: ":0"
      QT_X11_NO_MITSHM: "1"
```

### Example 2: Custom GPU-Enabled Build

```yaml
components:
  - name: yolo_detect
    build: docker/yolo
    runs_on: orin
    devices:
      - /dev/video0:/dev/video0
    entrypoint: ros2 launch yolo_detector detect.launch.py
    optimisations:
      - shm: "2g"
      - ipc: "host"
```

**Dockerfile** (`docker/yolo/Dockerfile`):
```dockerfile
FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

# Install ROS 2 Humble
RUN apt-get update && apt-get install -y \
    curl gnupg lsb-release && \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null && \
    apt-get update && apt-get install -y \
    ros-humble-ros-base \
    python3-colcon-common-extensions

# Install YOLO dependencies
RUN pip3 install ultralytics opencv-python

# Copy detection package
COPY yolo_detector /ros_ws/src/yolo_detector
RUN . /opt/ros/humble/setup.sh && \
    cd /ros_ws && \
    colcon build

WORKDIR /ros_ws
```

### Example 3: Mixing Build Types

```yaml
components:
  # Forge-managed build
  - name: motion
    source: ros/src/leremix_control
    repositories:
      - url: https://github.com/ros-controls/ros2_control.git
        version: humble
    runs_on: pi
    entrypoint: ros2 launch leremix_control motion.launch.py

  # External image
  - name: rosboard
    image: thehale/rosboard:latest
    runs_on: pi
    ports:
      - "8888:8888"

  # Custom Dockerfile
  - name: camera_driver
    build: docker/camera
    runs_on: orin
    devices:
      - /dev/video0:/dev/video0
    entrypoint: ros2 launch camera driver.launch.py
```

## Build Process

### Forge-Managed Build
1. Generates Dockerfile in `.forge/workspaces/{component}`
2. Copies source packages into build context
3. Builds with `docker buildx` for target architecture
4. Pushes to registry

### External Image
1. Skips build entirely
2. Uses image as-is in docker-compose
3. Pulls during deploy

### Custom Dockerfile Build
1. Uses your Dockerfile from `build` directory
2. Build context is the specified directory
3. Builds with `docker buildx` for target architecture
4. Pushes to registry

## Validation

The configuration validator ensures:
- Only one build method per component
- `image` and `build` don't specify forge build options
- All components have `runs_on` (except simulated ones)
- Custom Dockerfiles exist at specified paths

## Migration Guide

### From Forge-Managed to Custom Dockerfile

If you need more control, migrate from managed builds:

**Before**:
```yaml
- name: camera
  source: ros/src/camera_driver
  apt_packages:
    - v4l-utils
  runs_on: orin
```

**After**:
Create `docker/camera/Dockerfile`:
```dockerfile
FROM {base_image}

RUN apt-get update && apt-get install -y v4l-utils
COPY camera_driver /ros_ws/src/camera_driver
RUN . /opt/ros/humble/setup.sh && cd /ros_ws && colcon build
```

Update config:
```yaml
- name: camera
  build: docker/camera
  runs_on: orin
```

### From External Image to Custom Dockerfile

If you need to customize a community image:

**Before**:
```yaml
- name: nav2
  image: osrf/ros:humble-navigation
  runs_on: robot
```

**After**:
Create `docker/nav2/Dockerfile`:
```dockerfile
FROM osrf/ros:humble-navigation

# Add custom navigation configs
COPY nav2_params.yaml /config/
RUN apt-get update && apt-get install -y my-custom-package
```

Update config:
```yaml
- name: nav2
  build: docker/nav2
  runs_on: robot
```
