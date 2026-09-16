# core/models.py
import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Host:
    name: str
    ip: str
    user: str
    arch: str
    port: int = 2375
    manager: bool = False
    dds_ip: Optional[str] = None  # Secondary IP for DDS communication
    mount_root: Optional[str] = None  # Remote mount root directory
    build_on_device: bool = False  # Build components on this device instead of locally

    @property
    def effective_dds_ip(self) -> str:
        """Return dds_ip if set, otherwise fall back to ip."""
        return self.dds_ip if self.dds_ip else self.ip

    @property
    def effective_mount_root(self) -> str:
        """Return mount_root if set, otherwise fall back to default."""
        return self.mount_root if self.mount_root else f"/home/{self.user}/forge-artifacts"

@dataclass
class RepositorySpec:
    url: str
    version: str
    folder: Optional[str] = None

    @classmethod
    def from_dict(cls, d):
        url = d['url']
        version = d['version']
        folder = d.get('folder')

        # Auto-derive folder from URL if not specified
        if not folder:
            # Extract repo name from URL (e.g., https://github.com/user/repo.git -> repo)
            folder = url.rstrip('/').split('/')[-1]
            if folder.endswith('.git'):
                folder = folder[:-4]

        return cls(url=url, version=version, folder=folder)

@dataclass
class CommonPackage:
    """Represents a common package that can be either VCS-based or local source-based"""
    name: str
    repositories: List[RepositorySpec] = field(default_factory=list)  # VCS-based
    source: List[str] = field(default_factory=list)  # Local folder-based

    @classmethod
    def from_dict(cls, d):
        """Parse common_package from dict, supporting both repositories and source formats"""
        name = d['name']

        # Parse repositories if present
        repos = []
        if 'repositories' in d:
            repos = [RepositorySpec.from_dict(r) for r in d['repositories']]

        # Parse source folders if present
        source = d.get('source', [])
        if isinstance(source, str):
            source = [source]  # Convert single string to list

        return cls(name=name, repositories=repos, source=source)

    @property
    def is_vcs_based(self) -> bool:
        """Returns True if this package uses VCS repositories"""
        return bool(self.repositories)

    @property
    def is_local_based(self) -> bool:
        """Returns True if this package uses local source folders"""
        return bool(self.source)

@dataclass
class Component:
    name: str
    # Source configuration (mutually exclusive)
    sources: List[str] = field(default_factory=list)  # Multiple source paths
    source: Optional[str] = None                      # Single source path
    folder: Optional[str] = None                      # Legacy (deprecated)
    build: Optional[str] = None                       # Path to custom Dockerfile directory
    image: Optional[str] = None                       # External pre-built image

    entrypoint: str = ""
    launch_args: str = ""
    devices: List[str] = field(default_factory=list)
    ports:   List[str] = field(default_factory=list)
    environment: dict = field(default_factory=dict)  # Environment variables
    preinstall:  List[str] = field(default_factory=list)
    runs_on: Optional[str] = None
    postinstall: List[str] = field(default_factory=list)
    repositories: List[RepositorySpec] = field(default_factory=list)
    apt_packages: List[str] = field(default_factory=list)
    pip_packages: List[str] = field(default_factory=list)
    workspace_dir: str = "ros_ws"  # Configurable workspace directory name
    # Performance optimisations
    shm_size: Optional[str] = None     # e.g., "512m"
    ipc_mode: Optional[str] = None     # e.g., "host"
    cpuset: Optional[str] = None       # e.g., "0,1" for pinned cores
    mount_shm: bool = False            # Mount /dev/shm from host
    rt_enabled: bool = False           # Enable real-time kernel capabilities

    # Docker runtime options
    privileged: bool = False           # Run container in privileged mode
    runtime: Optional[str] = None      # Container runtime (e.g., "nvidia")
    gpu_count: Optional[int] = None    # Number of GPUs (for nvidia runtime)
    gpu_device_ids: List[str] = field(default_factory=list)  # Specific GPU IDs (e.g., ["0", "1"])
    nvidia: bool = False               # Enable NVIDIA GPU support
    gui: bool = False                  # Enable X11 GUI forwarding
    volumes: List[str] = field(default_factory=list)  # Additional volume mounts
    stdin_open: bool = False           # Keep stdin open (docker -i)
    tty: bool = False                  # Allocate pseudo-TTY (docker -t)

    # GPU and GUI options
    nvidia: bool = False               # Enable NVIDIA GPU support
    gui: bool = False                  # Enable X11/GUI forwarding

    # Additional container options
    volumes: List[str] = field(default_factory=list)  # Additional volume mounts
    stdin_open: bool = False           # Keep stdin open (docker -i)
    tty: bool = False                  # Allocate pseudo-TTY (docker -t)

    @classmethod
    def from_dict(cls, d, is_common=False, workspace_dir="ros_ws"):
        repos = [RepositorySpec.from_dict(r) for r in d.get('repositories', [])]

        # Handle source fields and backward compatibility
        sources = d.get('sources', [])
        source = d.get('source')
        folder = d.get('folder')
        build = d.get('build')
        image = d.get('image')

        # Normalize source field: if source is a list, move to sources
        if source and isinstance(source, list):
            sources = source
            source = None

        # Backward compatibility warning
        if folder and not sources and not source and not build and not image:
            print(f"WARNING: Component '{d['name']}' uses deprecated 'folder' field. "
                  f"Consider migrating to 'source' or 'sources' fields.")
            source = folder  # Migrate folder to source
            folder = None

        # Parse optimisations
        shm_size = None
        ipc_mode = None
        cpuset = None
        mount_shm = False
        rt_enabled = False
        optimisations = d.get('optimisations', [])
        if optimisations:
            for opt in optimisations:
                if 'shm' in opt:
                    shm_size = opt['shm']
                elif 'ipc' in opt:
                    ipc_mode = opt['ipc']
                elif 'pinned_cores' in opt:
                    cores = opt['pinned_cores']
                    # Convert list [0, 1] to string "0,1"
                    if isinstance(cores, list):
                        cpuset = ','.join(map(str, cores))
                    else:
                        cpuset = str(cores)
                elif 'mount_shm' in opt:
                    mount_shm = opt['mount_shm']
                elif 'rt' in opt:
                    rt_enabled = opt['rt']

        # Parse docker runtime options
        privileged = d.get('privileged', False)
        runtime = d.get('runtime')
        gpu_count = d.get('gpu_count')
        gpu_device_ids = d.get('gpu_device_ids', [])
        if isinstance(gpu_device_ids, str):
            gpu_device_ids = [gpu_device_ids]  # Convert single string to list
        nvidia = d.get('nvidia', False)
        gui = d.get('gui', False)
        volumes = d.get('volumes', [])
        stdin_open = d.get('stdin_open', False)
        tty = d.get('tty', False)

        # Parse GPU and GUI options
        nvidia = d.get('nvidia', False)
        gui = d.get('gui', False)

        # Parse additional container options
        volumes = d.get('volumes', [])
        stdin_open = d.get('stdin_open', False)
        tty = d.get('tty', False)

        return cls(
            name        = d['name'],
            sources     = sources,
            source      = source,
            folder      = folder,
            build       = build,
            image       = image,
            entrypoint  = d.get('entrypoint', ""),
            launch_args = d.get('launch_args', ""),
            devices     = d.get('devices', []),
            ports       = d.get('ports', []),
            environment = d.get('environment', {}),
            preinstall  = d.get('preinstall', []),
            postinstall = d.get('postinstall', []),
            repositories= repos,
            apt_packages= d.get('apt_packages', []),
            pip_packages= d.get('pip_packages', []),
            runs_on     = d.get('runs_on', None),
            workspace_dir= workspace_dir,
            shm_size    = shm_size,
            ipc_mode    = ipc_mode,
            cpuset      = cpuset,
            mount_shm   = mount_shm,
            rt_enabled  = rt_enabled,
            privileged  = privileged,
            runtime     = runtime,
            gpu_count   = gpu_count,
            gpu_device_ids = gpu_device_ids,
            nvidia      = nvidia,
            gui         = gui,
            volumes     = volumes,
            stdin_open  = stdin_open,
            tty         = tty,
        )

    @property
    def managed_workspace(self) -> str:
        """Path to the managed workspace in .forge/workspaces/{name}"""
        return f".forge/workspaces/{self.name}"

    @property
    def workspace_src(self) -> str:
        """Path to src directory in managed workspace"""
        return os.path.join(self.managed_workspace, "src")

    @property
    def comp_src(self):
        """Legacy property for backward compatibility"""
        if self.folder:
            # Legacy path for backward compatibility
            return os.path.join(self.folder, self.workspace_dir, "src")
        else:
            # New managed workspace path
            return self.workspace_src

    @property
    def repos_file(self):
        """Path to repos.yaml file in managed workspace"""
        if self.folder:
            # Legacy path for backward compatibility
            return os.path.join(self.folder, self.workspace_dir, "repos.yaml")
        else:
            # New managed workspace path
            return os.path.join(self.managed_workspace, "repos.yaml")

    def get_source_paths(self) -> List[str]:
        """Get all source paths for this component"""
        if self.sources:
            return self.sources
        elif self.source:
            return [self.source]
        elif self.folder:
            # Legacy support: assume folder contains workspace_dir/src
            return [os.path.join(self.folder, self.workspace_dir, "src")]
        return []

    def image_tag(self, cfg):
        if self.image:
            return self.image
        return f"{cfg.registry}/{cfg.image_prefix}_{self.name}:{cfg.tag}"
