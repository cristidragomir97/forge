# Commands

Forge provides a simple workflow for building and deploying ROS 2 systems.

## Workflow Overview

```
init → prep → stage → build → launch
```

1. **init** - Bootstrap a new project
2. **prep** - Create the base image with common packages
3. **stage** - Generate component images with dependencies
4. **build** - Compile ROS workspaces
5. **launch** - Deploy and run on target hosts

---

## init

**Command**: `forge <project_folder> init`

Bootstrap a new project in the specified directory. Creates the initial project structure and configuration files.

**Example:**
```bash
forge my_robot init
```

---

## prep

**Command**: `forge <project_folder> prep`

Creates a base image with the specified `ros_distro` and including the `common_packages`.

**When to re-run:**
- After adding a new common package
- After changing the ROS distribution
- After modifying global `apt_packages`

**Example:**
```bash
forge my_robot prep
```

---

## stage

**Command**: `forge <project_folder> stage`

The stage step prepares each component's container image with all required dependencies, but without compiling or adding the actual application code yet.

**What happens during stage:**

1. The base image is checked for changes and rebuilt only if needed (using hash-based caching)
2. System dependencies (apt packages) and ROS packages from remote repositories (VCS) are installed
3. The container ends up with a fully configured environment, ready for building
4. `docker-compose.yaml` files for each host are generated with container settings

Each built image then needs to get onto its target host. By default (`deploy_mode: image`) that's a registry push (from stage) + pull (from stage/sync/launch). Setting `deploy_mode: transfer` in `config.yaml` skips the registry entirely: images are built with `--load` instead of `--push`, then `docker save`d locally and `docker load`ed directly onto each host over its Docker API — no registry credentials or network access to a registry needed. See [Configuration](configuration.md).

**For different component types:**
- **Forge-managed**: Dependencies installed, ready for build step
- **External image**: No build, image reference added to compose file
- **Custom Dockerfile**: Docker build executed during this step

**Flags:**

| Flag | Description |
|------|-------------|
| `--refresh` | Only regenerate `docker-compose.yaml` files, skip builds |
| `--force-base` | Force rebuild of base image even if cached |
| `-c, --component <name>` | Stage only the specified component |

**Examples:**
```bash
# Stage all components
forge my_robot stage

# Stage single component
forge my_robot stage -c perception

# Refresh compose files only
forge my_robot stage --refresh

# Force base image rebuild
forge my_robot stage --force-base
```

---

## build

**Command**: `forge <project_folder> build`

Compiles the ROS workspace for each component using the environment prepared during stage.

**What happens during build:**

1. The corresponding stage container is started locally
2. The component's workspace is mounted from `.forge/build/{component}/ros_ws/`
3. The workspace is built using colcon
4. Artifacts are written to `install/` and `build/` folders
5. Artifacts are not embedded in the image, keeping it clean and enabling fast rebuilds

**Flags:**

| Flag | Description |
|------|-------------|
| `-c, --component <name>` | Build only the specified component |

**Examples:**
```bash
# Build all components
forge my_robot build

# Build single component
forge my_robot build -c perception
```

---

## launch

**Command**: `forge <project_folder> launch`

Syncs compiled components to target hosts and launches containers.

**What happens during launch:**

1. Changed files are transferred using rsync (for remote hosts)
2. Docker compose files are copied to each host
3. Containers are started on each host

**Flags:**

| Flag | Description |
|------|-------------|
| `--host <name>` | Only launch on this specific host |

**Examples:**
```bash
# Launch on all hosts
forge my_robot launch

# Launch on specific host
forge my_robot launch --host rpi5
```

---

## pixi

**Command**: `forge <project_folder> pixi`

Opens a shell with a RoboStack/pixi environment configured with your robot's middleware settings (DDS or Zenoh).

**What it does:**

1. Activates the pixi environment
2. Sets `ROS_DOMAIN_ID` and `ROS_DISTRO`
3. Configures the appropriate RMW:
   - **FastDDS**: Sets `FASTRTPS_DEFAULT_PROFILES_FILE` or `ROS_DISCOVERY_SERVER`
   - **Zenoh**: Sets `RMW_IMPLEMENTATION=rmw_zenoh_cpp` and `ZENOH_ROUTER`
4. Stops the ROS 2 daemon to avoid discovery conflicts
5. Launches an interactive shell

**Prerequisites:**
- [pixi](https://pixi.sh/) must be installed
- A `pixi.toml` or `pyproject.toml` must exist in the project
- Run `forge stage` first to generate middleware configuration files

**Example:**
```bash
forge my_robot pixi
```

---

## Common Workflows

### Initial Setup
```bash
forge my_robot init
# Edit config.yaml
forge my_robot prep
forge my_robot stage
forge my_robot build
forge my_robot launch
```

### Iterative Development
```bash
# After code changes
forge my_robot build -c my_component
forge my_robot launch
```

### Adding Dependencies
```bash
# After adding apt/pip packages or repositories to a component
forge my_robot stage -c my_component
forge my_robot build -c my_component
forge my_robot launch
```

### Adding Common Packages
```bash
# After adding common_packages
forge my_robot prep
forge my_robot stage
forge my_robot build
forge my_robot launch
```
