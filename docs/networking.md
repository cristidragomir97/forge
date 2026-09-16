# Networking

Forge is designed to support robust, multi-host ROS 2 deployments using a structured yet flexible approach to communication between containers and physical machines.

## Overview

The goal is to make multi-machine setups (like robot + workstation or multiple hosts) behave as a single unified ROS 2 system, without requiring custom bridging, remapping, or brittle configuration hacks.

**Key design decisions:**

- All containers use **host networking** by default
- The middleware can directly use multicast, broadcast, and unicast for discovery
- No need to expose individual container ports or deal with NAT
- Tools like `ros2 topic echo`, `rviz2`, or `ros2 node list` work across hosts

As long as your hosts are defined correctly in `config.yaml` and are on the same subnet, everything should work seamlessly.

---

## ROS Middleware (RMW) Options

Forge supports two ROS 2 middleware implementations:

| Feature | FastDDS | Zenoh |
|---------|---------|-------|
| Default | Yes | No |
| Discovery | Discovery Server | Zenoh Router |
| WAN Support | Limited | Excellent |
| Latency | Good | Lower |
| Memory Footprint | Standard | Smaller |
| ROS 2 Support | All distros | Jazzy+ (others need manual setup) |

---

## FastDDS (Default)

FastDDS is the default RMW implementation. Forge automatically provisions a FastDDS Discovery Server to avoid the limitations of peer-to-peer discovery at scale.

### Configuration

```yaml
rmw_implementation: fastdds  # or omit entirely (default)

# Optional
enable_dds_router: false
discovery_server: localhost
```

### How It Works

1. A **discovery server** container is launched on the manager host
2. All other containers act as **superclients** and register with this server
3. This centralizes discovery and reduces multicast traffic
4. Each component gets a `superclient.xml` configuration file

### Environment Variables Set

```bash
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
FASTRTPS_DEFAULT_PROFILES_FILE=/superclient.xml
ROS_DISCOVERY_SERVER=<manager_ip>:11811
```

### Local Development

When using `forge pixi`, the superclient configuration is automatically loaded from `.forge/superclient.xml` (generated during `forge stage`).

---

## Zenoh

[Zenoh](https://zenoh.io/) is a modern pub/sub protocol offering several advantages over traditional DDS:

- **Lower latency**: Optimized for real-time communication
- **Better WAN support**: Works seamlessly across networks and through firewalls
- **Smaller footprint**: Lower memory and CPU usage
- **Simpler configuration**: No complex QoS tuning required

### Configuration

```yaml
rmw_implementation: zenoh

# Optional Zenoh configuration
zenoh:
  router_image: eclipse-zenoh/zenoh:latest  # Docker image for router
  router_port: 7447                          # Router listening port
```

### How It Works

1. A **Zenoh router** container is launched on the manager host
2. All component containers connect to the router
3. The router handles message routing between nodes

### Environment Variables Set

```bash
RMW_IMPLEMENTATION=rmw_zenoh_cpp
ZENOH_ROUTER=tcp://<manager_ip>:7447
```

### Local Development

When using `forge pixi` with Zenoh configured, the shell is set up with:

```bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_ROUTER=tcp://<manager_ip>:7447
```

### Availability

| ROS 2 Distro | Zenoh Support |
|--------------|---------------|
| Jazzy+ | Included by default |
| Humble/Iron | Requires manual installation or RoboStack |

To use Zenoh with Humble/Iron, you can:
- Build `rmw_zenoh_cpp` from source
- Use a RoboStack environment that includes it

---

## Multi-NIC Setups

If your robot has multiple network interfaces, you can specify which IP to use for middleware communication:

```yaml
hosts:
  - name: robot
    ip: robot.local           # SSH/management IP
    dds_ip: 192.168.1.100     # IP for ROS 2 communication
    user: ubuntu
    arch: arm64
    manager: true
```

The `dds_ip` field is used for:
- FastDDS Discovery Server binding
- Zenoh Router binding
- Superclient configuration

---

## Manager Host

One host should be designated as the **manager** to run the middleware router:

```yaml
hosts:
  - name: main_computer
    ip: 192.168.1.100
    user: robot
    arch: amd64
    manager: true    # This host runs the discovery server / Zenoh router

  - name: sensor_node
    ip: 192.168.1.101
    user: robot
    arch: arm64
    # Not a manager - connects to the router on main_computer
```

If no host is marked as manager, the first host in the list is used.

---

## Firewall Configuration

Ensure these ports are open between hosts:

### FastDDS

| Port | Protocol | Purpose |
|------|----------|---------|
| 11811 | TCP/UDP | Discovery Server |
| 7400-7500 | UDP | DDS data traffic |

### Zenoh

| Port | Protocol | Purpose |
|------|----------|---------|
| 7447 | TCP | Zenoh Router |

---

## Troubleshooting

### Nodes can't discover each other

1. **Check network connectivity**: Can hosts ping each other?
2. **Check firewall rules**: Are the required ports open?
3. **Verify manager host**: Is the discovery server / Zenoh router running?
4. **Check ROS_DOMAIN_ID**: All nodes must use the same domain ID

### High latency or dropped messages

1. **Network bandwidth**: Use Ethernet or fast WiFi (6E/7)
2. **Consider Zenoh**: Better performance over congested networks
3. **Check QoS settings**: Mismatched QoS can cause issues

### Local development can't connect to robot

1. Run `forge stage` to generate middleware config files
2. Use `forge pixi` to get a properly configured shell
3. Ensure your dev machine is on the same network as the robot
