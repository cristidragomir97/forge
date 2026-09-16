# Multi-Host Systems

One of the most powerful capabilities of forge is support for multi-host systems where different parts of your ROS 2 stack run on different physical machines but function as a single, seamless graph.

## Overview

By defining multiple `hosts` in your config and assigning components to them via the `runs_on` field, forge enables you to shift computation between machines with minimal effort.

**What forge handles automatically:**
- Networking and middleware discovery configuration
- Cross-architecture builds (amd64, arm64, armv7)
- Syncing compiled artifacts to each host
- Getting built images onto each host, via a registry or direct transfer (see [Image Deployment](#image-deployment-registry-or-direct-transfer) below)
- Generating per-host docker-compose files

---

## Example 1: Dev Machine to Robot Migration

During early development, run CPU-intensive components on your dev machine. Later, move them to the robot with a single config change.

### Development Phase

```yaml
hosts:
  - name: devmachine
    ip: 127.0.0.1
    user: developer
    arch: amd64
    manager: true

  - name: robot
    ip: robot.local
    user: ubuntu
    arch: arm64

components:
  - name: perception
    source: components/perception
    runs_on: devmachine    # Run on dev machine during development

  - name: drivers
    source: components/drivers
    runs_on: robot
    devices:
      - "/dev:/dev"
```

### Production Phase

Simply change `runs_on`:

```yaml
components:
  - name: perception
    source: components/perception
    runs_on: robot         # Move to robot for deployment

  - name: drivers
    source: components/drivers
    runs_on: robot
    devices:
      - "/dev:/dev"
```

Then rebuild and deploy:

```bash
forge stage
forge build
forge launch
```

Forge automatically:
- Rebuilds the component for arm64
- Syncs artifacts to the robot
- Integrates it into the same ROS 2 domain

---

## Example 2: Distributed Perception

A robot with multiple cameras, each connected to a separate Jetson for local inference, with a central computer for aggregation.

```yaml
hosts:
  - name: main_computer
    ip: 192.168.1.100
    user: robot
    arch: amd64
    manager: true

  - name: jetson_front
    ip: 192.168.1.101
    user: robot
    arch: arm64
    build_on_device: true   # Build natively on Jetson

  - name: jetson_side
    ip: 192.168.1.102
    user: robot
    arch: arm64
    build_on_device: true

  - name: jetson_rear
    ip: 192.168.1.103
    user: robot
    arch: arm64
    build_on_device: true

components:
  - name: front_inference
    source: components/perception
    runs_on: jetson_front
    nvidia: true
    environment:
      CAMERA_ID: front

  - name: side_inference
    source: components/perception
    runs_on: jetson_side
    nvidia: true
    environment:
      CAMERA_ID: side

  - name: rear_inference
    source: components/perception
    runs_on: jetson_rear
    nvidia: true
    environment:
      CAMERA_ID: rear

  - name: perception_fusion
    source: components/fusion
    runs_on: main_computer
```

### Benefits

- Each Jetson processes data close to the sensor (low latency)
- Main computer receives compact, semantic data (not raw images)
- All components participate in a unified ROS 2 graph
- Automatic cross-architecture builds

---

## Example 3: High-Performance Workstation + Edge Devices

Run heavy computation (SLAM, planning) on a powerful workstation while edge devices handle sensors.

```yaml
hosts:
  - name: workstation
    ip: 192.168.1.50
    user: developer
    arch: amd64
    manager: true

  - name: robot_base
    ip: 192.168.1.100
    user: robot
    arch: arm64

components:
  # Heavy computation on workstation
  - name: slam
    source: components/slam
    runs_on: workstation

  - name: navigation
    source: components/navigation
    runs_on: workstation

  - name: planning
    source: components/planning
    runs_on: workstation

  # Sensors and actuation on robot
  - name: lidar_driver
    source: components/lidar
    runs_on: robot_base
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"

  - name: motor_controller
    source: components/motors
    runs_on: robot_base
    devices:
      - "/dev/ttyACM0:/dev/ttyACM0"
```

---

## Cross-Architecture Builds

When a component targets a different architecture than your dev machine:

### Option 1: Emulated Build (Default)

Forge uses Docker's buildx with QEMU emulation. This is slower but requires no setup on the target device.

### Option 2: Native Build on Device (Recommended)

Set `build_on_device: true` on the host to build everything directly on the target:

```yaml
hosts:
  - name: jetson
    ip: jetson.local
    user: nvidia
    arch: arm64
    build_on_device: true   # All builds happen on the Jetson
```

When enabled, all build operations happen natively on the device:
- **Base images** (forge prep) are built on the device
- **Component images** (forge stage) are built on the device
- **ROS workspaces** (forge build) are compiled on the device

This is **much faster** for ARM64 targets when your dev machine is x86_64 (often 10x or more).

---

## Image Deployment: Registry or Direct Transfer

Once images are built, forge has to get them onto each host. Two modes, set via `deploy_mode` in `config.yaml`:

### `deploy_mode: image` (Default)

`stage` pushes built images to `registry`; `sync` and `launch` pull them on each host. Standard Docker registry workflow — needs registry credentials and network access to it from both your dev machine and every host.

### `deploy_mode: transfer`

No registry involved. Images are built locally with `docker build --load` (kept in your local Docker daemon instead of pushed), then `docker save`d and `docker load`ed directly onto each host over its Docker API (`host.ip:host.port`) — the same connection forge already uses to pull images and run compose. Useful when hosts can't reach a registry (air-gapped robots, local-only networks) or you'd rather not stand one up.

```yaml
registry: local          # still required as an image-name prefix, just never pushed to
image_prefix: myrobot
deploy_mode: transfer
```

This applies to any host that isn't `build_on_device` (those build directly on the target already, so there's nothing to transfer) or `localhost` (the image is already in the local daemon).

---

## Network Topology

### Single Subnet (Recommended)

All hosts on the same network segment:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Workstation │     │    Robot    │     │   Jetson    │
│ 192.168.1.50 │────│192.168.1.100│────│192.168.1.101│
│   (manager)  │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                    Same subnet
```

### Multiple NICs

Use `dds_ip` for hosts with multiple network interfaces:

```yaml
hosts:
  - name: robot
    ip: robot.local          # Management interface
    dds_ip: 192.168.1.100    # ROS communication interface
    user: ubuntu
    arch: arm64
```

---

## Generated Files

For multi-host deployments, forge generates:

```
project/
├── docker-compose.workstation.yaml
├── docker-compose.robot_base.yaml
├── docker-compose.jetson_front.yaml
└── ...
```

Each file contains only the components for that host, plus middleware configuration if it's the manager.

---

## Tips

### Start Simple

Begin with everything on one machine, then distribute as needed:

```yaml
# Start here
components:
  - name: everything
    runs_on: devmachine

# Then split
components:
  - name: perception
    runs_on: jetson
  - name: planning
    runs_on: devmachine
```

### Use Consistent Naming

Name hosts by their role or location for clarity:

```yaml
hosts:
  - name: control_computer    # Not "pc1"
  - name: front_sensor_unit   # Not "jetson2"
  - name: actuator_node       # Not "rpi"
```

### Monitor Network Usage

When distributing components, be mindful of data flowing between hosts:
- Camera images are large
- Point clouds are very large
- Consider compression or local processing
