# Platform Notes

Forge supports development on macOS, Linux, and Windows (via WSL). Each platform has different capabilities and limitations.

## Platform Comparison

| Feature | Linux | macOS | WSL |
|---------|-------|-------|-----|
| Host networking | Yes | No | Limited |
| Hybrid graphs (local + container) | Yes | No | No |
| GUI containers | Yes | Limited | Yes (WSLg) |
| ARM64 cross-compilation | Slow (QEMU) | Fast (native) | Slow (QEMU) |
| NVIDIA GPU passthrough | Yes | No | Yes |

---

## macOS

### Advantages

- **Fast ARM64 builds**: Apple Silicon Macs can build ARM64 images natively, making cross-compilation for Jetson/RPi extremely fast
- **Great for development**: Excellent for writing code and managing deployments

### Limitations

- **No host networking**: Docker runs inside a Linux VM, so containers can't share the host network
- **No hybrid graphs**: Can't mix local ROS nodes with containerized ones
- **No GUI containers**: X11 forwarding is limited

### Workarounds

#### Local Development

Use [RoboStack](https://robostack.github.io/) with pixi for local ROS development:

```bash
# Install pixi
curl -fsSL https://pixi.sh/install.sh | bash

# Add ROS packages
pixi add ros-humble-desktop

# Activate with forge config
forge my_robot pixi
```

#### Remote Visualization

Run visualization tools on a Linux machine or the robot itself via VNC:

```yaml
components:
  - name: vnc
    image: ghcr.io/tiryoh/ros2-desktop-vnc:humble
    runs_on: robot
    ports:
      - "6080:80"
```

#### X11 Forwarding (Limited)

For simple GUI apps, install XQuartz and enable connections:

```bash
# Install XQuartz
brew install --cask xquartz

# Allow connections (after XQuartz restart)
xhost +localhost
```

---

## Linux

### Full Support

Linux has full support for all forge features:
- Host networking for seamless ROS communication
- Hybrid computation graphs
- GUI containers with X11
- NVIDIA GPU passthrough

### ARM64 Emulation

Building ARM64 images on x86_64 Linux uses QEMU emulation, which is slow. Options:

#### Option 1: Build on Device (Recommended)

Set `build_on_device: true` for ARM64 hosts. This builds **all images** (base, component, and workspaces) natively on the device:

```yaml
hosts:
  - name: jetson
    ip: jetson.local
    user: nvidia
    arch: arm64
    build_on_device: true  # All builds happen on the Jetson
```

When `build_on_device: true`:
- `forge prep` builds the base image on the device
- `forge stage` builds component images on the device
- `forge build` compiles ROS workspaces on the device

This is **much faster** than QEMU emulation (often 10x or more).

#### Option 2: Use a Mac for ARM64 Builds

If you have an Apple Silicon Mac, use it for ARM64 builds (they run natively).

### NVIDIA GPU Support

Enable GPU access for containers:

```yaml
components:
  - name: inference
    source: components/inference
    runs_on: workstation
    nvidia: true
    # Or for specific GPUs:
    gpu_count: 2
    gpu_device_ids: ['0', '1']
```

Requirements:
- NVIDIA drivers installed
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

---

## Windows (WSL)

### Supported Features

- **WSLg**: GUI applications work via WSLg (Windows 11)
- **NVIDIA GPU**: Works with WSL2 GPU support
- **Development**: Good for code editing and local builds

### Limitations

- **No hybrid graphs**: WSL networking doesn't support host network mode properly
- **Performance**: Some overhead compared to native Linux

### Setup

1. Install WSL2 with Ubuntu:
   ```powershell
   wsl --install -d Ubuntu
   ```

2. Install Docker Desktop with WSL2 backend

3. Install forge in WSL:
   ```bash
   pip install .
   ```

### GUI Applications

WSLg should work automatically on Windows 11. Test with:

```bash
# In WSL
xclock
```

If not working, ensure WSLg is enabled in Docker Desktop settings.

---

## Docker Configuration

### Enabling TCP Socket

Forge requires Docker hosts to expose a TCP socket. This is needed for remote Docker operations.

#### On Target Hosts (Linux)

1. Create `/etc/docker/daemon.json`:
   ```json
   {
     "hosts": ["tcp://0.0.0.0:2375", "unix:///var/run/docker.sock"]
   }
   ```

2. Create `/etc/systemd/system/docker.service.d/override.conf`:
   ```ini
   [Service]
   ExecStart=
   ExecStart=/usr/bin/dockerd
   ```

3. Reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   ```

#### Security Note

The default configuration exposes Docker without authentication. This is acceptable on trusted networks. For production or untrusted networks, consider:
- Using SSH tunneling
- Enabling TLS authentication
- Using a VPN

---

## Recommended Development Setups

### macOS Developer

```
┌─────────────────┐
│  Mac (M1/M2/M3) │
│  - Code editing │
│  - forge CLI    │◄──── Fast ARM64 builds
│  - pixi/RoboStack│
└────────┬────────┘
         │ Deploy
         ▼
┌─────────────────┐
│  Robot (ARM64)  │
│  - All runtime  │
│  - VNC for viz  │
└─────────────────┘
```

### Linux Developer

```
┌─────────────────┐
│ Linux Workstation│
│  - Code editing │
│  - forge CLI    │
│  - rviz2 native │◄──── Hybrid graphs possible
│  - GPU compute  │
└────────┬────────┘
         │ Deploy
         ▼
┌─────────────────┐
│  Robot (ARM64)  │
│  - Sensors      │
│  - Actuation    │
└─────────────────┘
```

### WSL Developer

```
┌─────────────────┐
│ Windows + WSL   │
│  - Code editing │
│  - forge CLI    │
│  - WSLg for GUI │
└────────┬────────┘
         │ Deploy
         ▼
┌─────────────────┐
│  Robot (ARM64)  │
│  - All runtime  │
└─────────────────┘
```
