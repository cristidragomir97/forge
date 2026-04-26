# core/config.py
import os
import getpass
import yaml
from colorama import Fore
from .models import Host, Component, CommonPackage
from .validation import ConfigValidator, ForgeConfig
from .exceptions import ConfigurationError, SourceNotFoundError, ValidationError

class Config:
    def __init__(self, data, root):
        self.root            = root
        # … existing required/optional keys …


        # required
        self.ros_distro      = data['ros_distro']
        self.ros_domain_id   = data['ros_domain_id']
        self.registry        = data['registry']
        self.image_prefix    = data['image_prefix']

        self.enable_apt_caching = data.get('enable_apt_caching', True)

        # optional / with defaults
        self.deploy_mode     = data.get('deploy_mode', 'image')
        self.build_dir       = data.get('build_dir', '.forge/build')
        self.components_dir  = data.get('components_dir', 'components')
        self.workspace_dir   = data.get('workspace_dir', 'ros_ws')
        self.compose_file    = data.get('compose_file', 'docker-compose.yml')
        self.mount_root      = data.get('mount_root', f"/home/{getpass.getuser()}/ros_builds")
        self.docker_port     = data.get('docker_port', 2375)
        self.tag             = data.get('tag', 'latest')

        # RMW (ROS Middleware) configuration
        self.rmw_implementation = data.get('rmw_implementation', 'fastdds')
        zenoh_data = data.get('zenoh', {})
        self.zenoh_router_image = zenoh_data.get('router_image', 'eclipse-zenoh/zenoh:latest')
        self.zenoh_router_port = zenoh_data.get('router_port', 7447)
        self.zenoh_config_file = zenoh_data.get('config_file', None)

        # DDS configuration (used when rmw_implementation is fastdds)
        self.enable_dds_router = data.get('enable_dds_router', False)
        self.discovery_server = data.get('discovery_server', 'localhost')

        # Global container options
        self.local           = data.get('local', False)
        self.nvidia          = data.get('nvidia', False)
        self.gui             = data.get('gui', False)

        # Base image override (e.g., nvidia/cuda:12.0-devel-ubuntu22.04)
        self.base_image_override = data.get('base_image_override', None)

        # Apt mirrors (None = use defaults)
        self.apt_mirror      = data.get('apt_mirror', None)  # Ubuntu apt mirror
        self.ros_apt_mirror  = data.get('ros_apt_mirror', None)  # ROS apt mirror

        # NEW: system‐level apt packages for the base image
        self.apt_packages    = data.get('apt_packages', [])

        # coalesce None→[] for common & components
        common = data.get('common_packages') or []
        self.common_packages = [ CommonPackage.from_dict(c)
                                 for c in common ]

        comps  = data.get('components') or []
        self.components      = [ Component.from_dict(c, is_common=False, workspace_dir=self.workspace_dir)
                                 for c in comps ]

        # hosts: support either list or single dict
        raw_hosts = data.get('hosts') or data.get('host') or []
        self.hosts = [Host(**h) for h in raw_hosts]

    @classmethod
    def load(cls, project_root: str, config_file: str = 'config.yaml', validate: bool = True):
        """
        Load and optionally validate configuration.

        Args:
            project_root: Path to project directory
            config_file: Name or path to configuration file (default: 'config.yaml')
            validate: Run Pydantic validation (default: True)

        Returns:
            Config instance

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ConfigurationError: If validation fails
        """
        # Support both absolute paths and relative paths
        if os.path.isabs(config_file):
            path = config_file
        else:
            path = os.path.join(project_root, config_file)

        # Run validation if requested
        if validate:
            validator = ConfigValidator(project_root)
            try:
                validated_config, warnings = validator.validate_all(path)

                # Print warnings
                for warning in warnings:
                    print(Fore.YELLOW + f"[WARNING] {warning}")

            except (ConfigurationError, SourceNotFoundError, ValidationError, FileNotFoundError):
                # Re-raise validation errors with their context intact
                raise
            except Exception as e:
                # Wrap unexpected errors
                raise ConfigurationError(f"Unexpected validation error: {e}")

        # Load YAML (even if validation ran, we still need to load for backward compatibility)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Configuration file '{config_file}' not found at {path}")

        data = yaml.safe_load(open(path)) or {}
        return cls(data, project_root)

    @property
    def platforms(self):
        return [f"linux/{h.arch}" for h in self.hosts]

    @property
    def base_image(self):
        # Dynamically derived, no longer read from config.yaml
        return f"{self.registry}/{self.image_prefix}_base:{self.ros_distro}-{self.tag}"

    @property
    def is_zenoh(self) -> bool:
        """Check if Zenoh RMW is configured."""
        return self.rmw_implementation == 'zenoh'

    @property
    def is_fastdds(self) -> bool:
        """Check if FastDDS RMW is configured."""
        return self.rmw_implementation == 'fastdds'

    @property
    def rmw_implementation_value(self) -> str:
        """Returns the actual RMW implementation string for ROS."""
        return 'rmw_zenoh_cpp' if self.is_zenoh else 'rmw_fastrtps_cpp'

    def filter_components(self, name=None):
        comps = self.components
        if name:
            comps = [c for c in comps if c.name == name]
        return comps
