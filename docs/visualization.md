# Visualization

ROS development often requires GUI tools like rviz2, rqt, or Gazebo. Depending on your setup, you can either run these tools directly on the robot and view them remotely via VNC, or run them locally on your development machine.

## Options Overview

| Approach | Best For | Tradeoffs |
|----------|----------|-----------|
| VNC on Robot | Simple monitoring, mobile access | Limited by robot's GPU/CPU |
| VNC on Dev Machine | Heavy visualization, debugging | Uses network bandwidth |
| Native (pixi) | Fastest iteration, full tooling | Requires local ROS setup |

---

## Option 1: VNC on the Robot

Run a desktop environment container on the robot and connect via web browser or VNC client.

### How It Works

1. A container with OpenGL and virtual display support runs on the robot
2. A VNC server is exposed on a configurable port
3. Connect using a web browser (e.g., `http://robot-ip:6080`) or VNC client

### When to Use

- Robot has enough processing power for simple visualizations
- You want to monitor from any device (phone, tablet, etc.)
- Visualizations are simple (TF tree, 2D maps, basic rviz)

### Example Configuration

```yaml
hosts:
  - name: rpi5
    ip: pi5.local
    user: user
    arch: arm64

components:
  - name: camera
    source: components/camera
    runs_on: rpi5
    entrypoint: ros2 launch camera_bringup bringup.launch.py
    devices:
      - "/dev:/dev"

  - name: vnc
    image: ghcr.io/tiryoh/ros2-desktop-vnc:humble
    runs_on: rpi5
    ports:
      - "6080:80"
```

Access the desktop at `http://pi5.local:6080`

### Recommended Images

- [Tiryoh's docker-ros2-desktop-vnc](https://github.com/Tiryoh/docker-ros2-desktop-vnc) - Lightweight, well-maintained

---

## Option 2: VNC on Development Machine

Run visualization tools on your development machine with full GPU acceleration.

### How It Works

1. Add your dev machine as a host in config.yaml
2. Run the VNC container on your dev machine
3. Optionally enable NVIDIA GPU support for better performance

### When to Use

- Robot hardware is limited
- You need high-performance visualization (3D point clouds, complex rviz)
- Debugging hybrid robot+desktop computation graphs

### Example Configuration

```yaml
hosts:
  - name: rpi5
    ip: pi5.local
    user: user
    arch: arm64

  - name: devmachine
    ip: 127.0.0.1
    user: your_username
    arch: amd64

components:
  - name: camera
    source: components/camera
    runs_on: rpi5
    entrypoint: ros2 launch camera_bringup bringup.launch.py
    devices:
      - "/dev:/dev"

  - name: vnc
    image: ghcr.io/tiryoh/ros2-desktop-vnc:humble
    runs_on: devmachine
    nvidia: true          # Use local GPU
    ports:
      - "6080:80"
```

### Bandwidth Considerations

Running visualization remotely can saturate network bandwidth, especially with:
- Camera streams
- Point cloud data
- High-frequency sensor data

Consider using topic throttling or compression if you experience latency.

---

## Option 3: Native with pixi/RoboStack

Run ROS tools natively on your development machine using a conda-based environment.

### How It Works

1. Install [pixi](https://pixi.sh/)
2. Create a pixi environment with ROS packages
3. Use `forge pixi` to configure middleware settings

### When to Use

- Fastest iteration for development
- Full access to all ROS tools
- No container overhead

### Setup

```bash
# Initialize pixi project (if not already done)
pixi init
pixi add ros-humble-desktop

# Activate with forge's middleware config
forge my_robot pixi
```

The `forge pixi` command:
- Activates the pixi environment
- Sets `ROS_DOMAIN_ID` and `ROS_DISTRO`
- Configures DDS/Zenoh to connect to your robot

### Example Session

```bash
$ forge my_robot pixi
[pixi] Initializing robostack environment...
[pixi] ✓ pixi found
[pixi] ✓ pixi project found
[pixi] ✓ config loaded
[pixi] ✓ manager host: rpi5 (192.168.1.100)
[pixi] ✓ Using superclient.xml from .forge/superclient.xml

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RoboStack Environment Active (pixi)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ROS Distribution: humble
  ROS Domain ID:    0
  RMW:              rmw_fastrtps_cpp
  DDS Server:       192.168.1.100:11811
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$ ros2 topic list
/camera/image_raw
/tf
/tf_static

$ rviz2
# Opens rviz2 connected to your robot's ROS graph
```

---

## GUI Support in Containers

For components that need GUI access (not VNC-based), you can enable X11 forwarding:

```yaml
components:
  - name: gui_app
    source: components/gui_app
    runs_on: devmachine
    gui: true             # Enable X11 forwarding
    nvidia: true          # Optional: GPU acceleration
```

This mounts the X11 socket and sets `DISPLAY` appropriately.

### Platform Notes

| Platform | GUI Support |
|----------|-------------|
| Linux | Full support via X11 socket |
| macOS | Requires XQuartz, limited support |
| WSL | Works with WSLg |

See [Platform Notes](platform-notes.md) for details.
