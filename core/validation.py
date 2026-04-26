"""
Pydantic models for configuration validation.

Provides schema validation and type checking for forge configuration files.
"""

import os
from typing import List, Optional, Union, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .exceptions import ConfigurationError, ValidationError, SourceNotFoundError


class Architecture(str, Enum):
    """Supported target architectures."""
    AMD64 = "amd64"
    ARM64 = "arm64"
    ARMV7 = "armv7"


class RMWImplementation(str, Enum):
    """Supported ROS Middleware implementations."""
    FASTDDS = "fastdds"
    ZENOH = "zenoh"


class ZenohConfig(BaseModel):
    """Zenoh-specific configuration."""
    model_config = ConfigDict(extra='forbid')

    router_image: str = Field("eclipse-zenoh/zenoh:latest", description="Zenoh router Docker image")
    router_port: int = Field(7447, ge=1, le=65535, description="Zenoh router port")
    config_file: Optional[str] = Field(None, description="Path to custom zenoh.json5 config")


class HostConfig(BaseModel):
    """Configuration for a remote host."""
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., description="Unique host identifier")
    ip: str = Field(..., description="Host IP address or hostname")
    user: str = Field(..., description="SSH username")
    arch: Architecture = Field(..., description="Target architecture")
    port: int = Field(2375, description="Docker daemon port")
    manager: bool = Field(False, description="DDS discovery server manager role")
    dds_ip: Optional[str] = Field(None, description="Secondary IP for DDS communication (defaults to ip if not set)")
    mount_root: Optional[str] = Field(None, description="Remote mount root directory for builds (defaults to /home/{user}/forge-artifacts)")
    build_on_device: bool = Field(False, description="Build components on this device instead of locally (faster for cross-arch builds)")

    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v


class RepositorySpec(BaseModel):
    """VCS repository specification."""
    model_config = ConfigDict(extra='forbid')

    url: str = Field(..., description="Git repository URL")
    version: str = Field(..., description="Branch, tag, or commit")
    folder: Optional[str] = Field(None, description="Target folder name (auto-derived if not specified)")

    @field_validator('folder', mode='before')
    @classmethod
    def auto_derive_folder(cls, v, info):
        """Auto-derive folder from URL if not specified."""
        if v is None and 'url' in info.data:
            url = info.data['url']
            folder = url.rstrip('/').split('/')[-1]
            if folder.endswith('.git'):
                folder = folder[:-4]
            return folder
        return v


class CommonPackageConfig(BaseModel):
    """Configuration for common packages shared across components."""
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., description="Package identifier")
    repositories: List[RepositorySpec] = Field(default_factory=list, description="VCS repositories")
    source: Union[List[str], str, None] = Field(default=None, description="Local source paths")

    @field_validator('source', mode='before')
    @classmethod
    def normalize_source(cls, v):
        """Normalize source to list."""
        if isinstance(v, str):
            return [v]
        return v if v is not None else []

    @model_validator(mode='after')
    def validate_has_packages(self):
        """Ensure at least one package source is specified."""
        has_repos = bool(self.repositories)
        has_source = bool(self.source)

        if not has_repos and not has_source:
            raise ValueError(f"Common package '{self.name}' must specify either 'repositories' or 'source'")

        return self

    @property
    def is_vcs_based(self) -> bool:
        return bool(self.repositories)

    @property
    def is_local_based(self) -> bool:
        return bool(self.source)


class OptimisationConfig(BaseModel):
    """Performance optimization settings."""
    model_config = ConfigDict(extra='forbid')

    shm: Optional[str] = None
    ipc: Optional[str] = None
    pinned_cores: Optional[List[int]] = None
    mount_shm: Optional[bool] = None
    rt: Optional[bool] = None


class ComponentConfig(BaseModel):
    """Configuration for a deployable component."""
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., description="Component identifier")

    # Source configuration (mutually exclusive)
    sources: List[str] = Field(default_factory=list, description="Multiple source paths")
    source: Union[List[str], str, None] = Field(default=None, description="Single or multiple source paths")
    folder: Optional[str] = Field(None, description="Legacy folder field (deprecated)")
    build: Optional[str] = Field(None, description="Path to directory containing custom Dockerfile")
    image: Optional[str] = Field(None, description="External pre-built image")

    # Runtime configuration
    runs_on: Optional[str] = Field(None, description="Target host name")
    entrypoint: str = Field("", description="Container startup command")
    launch_args: str = Field("", description="Arguments for entrypoint")

    # Hardware and networking
    devices: List[str] = Field(default_factory=list, description="Device mappings")
    ports: List[str] = Field(default_factory=list, description="Port mappings")

    # Environment variables
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # Dependencies
    repositories: List[RepositorySpec] = Field(default_factory=list, description="VCS repositories")
    apt_packages: List[str] = Field(default_factory=list, description="APT packages to install")
    pip_packages: List[str] = Field(default_factory=list, description="Python packages to install")

    # Build hooks
    preinstall: List[str] = Field(default_factory=list, description="Pre-install commands")
    postinstall: List[str] = Field(default_factory=list, description="Post-install commands")

    # Advanced options
    workspace_dir: str = Field("ros_ws", description="Workspace directory name")

    # Performance optimizations
    optimisations: List[Dict[str, Any]] = Field(default_factory=list, description="Performance optimizations")

    # Docker runtime options
    privileged: bool = Field(False, description="Run container in privileged mode")
    runtime: Optional[str] = Field(None, description="Container runtime (e.g., 'nvidia')")
    gpu_count: Optional[int] = Field(None, description="Number of GPUs to allocate")
    gpu_device_ids: Union[List[str], str, None] = Field(default=None, description="Specific GPU device IDs")
    nvidia: bool = Field(False, description="Enable NVIDIA GPU support for this component")
    gui: bool = Field(False, description="Enable X11 GUI forwarding for this component")
    volumes: List[str] = Field(default_factory=list, description="Additional volume mounts (e.g., '/host/path:/container/path:rw' or 'named_vol:/path')")
    stdin_open: bool = Field(False, description="Keep stdin open (docker -i)")
    tty: bool = Field(False, description="Allocate a pseudo-TTY (docker -t)")

    # GPU and GUI options
    nvidia: bool = Field(False, description="Enable NVIDIA GPU support")
    gui: bool = Field(False, description="Enable X11/GUI forwarding")

    # Additional container options
    volumes: List[str] = Field(default_factory=list, description="Additional volume mounts")
    stdin_open: bool = Field(False, description="Keep stdin open (docker -i)")
    tty: bool = Field(False, description="Allocate pseudo-TTY (docker -t)")

    @field_validator('source', mode='before')
    @classmethod
    def normalize_source(cls, v):
        """Normalize source field."""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator('gpu_device_ids', mode='before')
    @classmethod
    def normalize_gpu_device_ids(cls, v):
        """Normalize gpu_device_ids to list."""
        if isinstance(v, str):
            return [v]
        return v if v is not None else []

    @model_validator(mode='after')
    def validate_source_configuration(self):
        """Ensure exactly one source configuration method is used."""
        has_sources = bool(self.sources)
        has_source = bool(self.source)
        has_folder = bool(self.folder)
        has_build = bool(self.build)
        has_image = bool(self.image)
        has_repos = bool(self.repositories)

        source_count = sum([has_sources, has_source, has_folder, has_build, has_image])

        # Must have at least one source method (or repos for managed builds)
        if source_count == 0 and not has_repos:
            raise ValueError(
                f"Component '{self.name}' must specify one of: sources, source, folder, build, image, or repositories"
            )

        # Only one source method allowed
        if source_count > 1:
            raise ValueError(
                f"Component '{self.name}' can only specify one of: sources, source, folder, build, or image"
            )

        # External images and custom builds shouldn't specify forge build options
        if (has_image or has_build) and (has_repos or self.apt_packages or self.pip_packages):
            raise ValueError(
                f"Component '{self.name}': When using 'image' or 'build', do not specify repositories, apt_packages, or pip_packages"
            )

        return self

    @model_validator(mode='after')
    def validate_runs_on_required(self):
        """Ensure components specify runs_on."""
        if not self.runs_on:
            raise ValueError(f"Component '{self.name}' must specify 'runs_on'")
        return self


class ForgeConfig(BaseModel):
    """Root configuration for forge project."""
    model_config = ConfigDict(extra='forbid')

    # Required fields
    ros_distro: str = Field(..., description="ROS 2 distribution (e.g., humble, iron)")
    ros_domain_id: int = Field(..., ge=0, le=232, description="ROS domain ID")
    registry: str = Field(..., description="Docker registry URL")
    image_prefix: str = Field(..., description="Docker image name prefix")

    # Optional fields with defaults
    enable_apt_caching: bool = Field(True, description="Enable BuildKit cache mounts for apt/pip/rosdep")
    deploy_mode: str = Field('image', description="Deployment mode")
    build_dir: str = Field('.forge/build', description="Build output directory")
    components_dir: str = Field('components', description="Components directory")
    workspace_dir: str = Field('ros_ws', description="ROS workspace directory name")
    workplace_folder: Optional[str] = Field(None, description="Workplace folder path")
    compose_file: str = Field('docker-compose.yml', description="Docker Compose filename")
    mount_root: Optional[str] = Field(None, description="Remote mount root directory")
    docker_port: int = Field(2375, description="Docker daemon port")
    tag: str = Field('latest', description="Docker image tag")

    # RMW (ROS Middleware) configuration
    rmw_implementation: RMWImplementation = Field(RMWImplementation.FASTDDS, description="RMW implementation: fastdds or zenoh")
    zenoh: Optional[ZenohConfig] = Field(default_factory=ZenohConfig, description="Zenoh configuration (used when rmw_implementation is zenoh)")

    # DDS configuration (used when rmw_implementation is fastdds)
    enable_dds_router: bool = Field(False, description="Enable DDS router")
    discovery_server: str = Field('localhost', description="Discovery server address")

    # Global container options
    local: bool = Field(False, description="Run all components locally instead of on remote hosts")
    nvidia: bool = Field(False, description="Enable NVIDIA GPU support globally")
    gui: bool = Field(False, description="Enable X11/GUI forwarding globally")

    # Base image override (e.g., nvidia/cuda:12.0-devel-ubuntu22.04 instead of ubuntu:22.04)
    base_image_override: Optional[str] = Field(None, description="Override the base image for Dockerfile.base (e.g., nvidia/cuda image)")

    # Apt mirror configuration
    apt_mirror: Optional[str] = Field(None, description="Custom Ubuntu apt mirror URL (e.g., 'http://mirrors.tuna.tsinghua.edu.cn/ubuntu')")
    ros_apt_mirror: Optional[str] = Field(None, description="Custom ROS apt mirror URL (e.g., 'http://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu')")

    # System packages
    apt_packages: List[str] = Field(default_factory=list, description="System-level apt packages")

    # Collections
    common_packages: List[CommonPackageConfig] = Field(default_factory=list, description="Shared packages")
    components: List[ComponentConfig] = Field(default_factory=list, description="Deployable components")
    hosts: List[HostConfig] = Field(default_factory=list, description="Target hosts")

    @field_validator('mount_root', mode='before')
    @classmethod
    def set_default_mount_root(cls, v):
        """Set default mount_root based on user."""
        if v is None:
            return f"/home/{os.getlogin()}/ros_builds"
        return v

    @field_validator('components')
    @classmethod
    def validate_unique_component_names(cls, v):
        """Ensure component names are unique."""
        names = [comp.name for comp in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Component names must be unique. Duplicates: {set(duplicates)}")
        return v

    @field_validator('hosts')
    @classmethod
    def validate_unique_host_names(cls, v):
        """Ensure host names are unique."""
        names = [host.name for host in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Host names must be unique. Duplicates: {set(duplicates)}")
        return v

    @model_validator(mode='after')
    def validate_component_host_references(self):
        """Ensure components reference valid hosts."""
        host_names = {host.name for host in self.hosts}

        for comp in self.components:
            if comp.runs_on and comp.runs_on not in host_names:
                raise ValueError(
                    f"Component '{comp.name}' references unknown host '{comp.runs_on}'. "
                    f"Available hosts: {', '.join(host_names)}"
                )

        return self


class ConfigValidator:
    """Validator for forge configuration with filesystem checks."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)

    def validate_config_file(self, config_path: str) -> ForgeConfig:
        """
        Validate config file and return parsed configuration.

        Raises:
            ConfigurationError: If config is invalid (includes all validation errors)
            FileNotFoundError: If config file doesn't exist
        """
        import yaml
        from pydantic import ValidationError as PydanticValidationError

        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Failed to parse YAML: {e}")

        try:
            config = ForgeConfig(**data)
        except PydanticValidationError as e:
            # Extract all error messages from Pydantic validation
            errors = []
            for error in e.errors():
                loc = " -> ".join(str(l) for l in error['loc'])
                msg = error['msg']
                errors.append(f"{loc}: {msg}")

            raise ConfigurationError(
                "Configuration validation failed",
                context={"errors": errors}
            )
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")

        return config

    def validate_source_paths_from_data(self, data: dict) -> tuple[List[str], List[str]]:
        """
        Validate that source paths exist in filesystem (from raw YAML data).

        Args:
            data: Raw YAML configuration dict

        Returns:
            Tuple of (errors, warnings)
        """
        warnings = []
        errors = []

        # Validate common package sources
        common_packages = data.get('common_packages', []) or []
        for pkg in common_packages:
            pkg_name = pkg.get('name', 'unknown')
            sources = pkg.get('source', [])
            if isinstance(sources, str):
                sources = [sources]

            for source_path in sources:
                abs_path = os.path.join(self.project_root, source_path)
                if not os.path.exists(abs_path):
                    errors.append(
                        f"Common package '{pkg_name}' source not found: {source_path} (absolute: {abs_path})"
                    )

        # Validate component sources
        components = data.get('components', []) or []
        for comp in components:
            comp_name = comp.get('name', 'unknown')
            source_paths = []

            # Handle different source field variants
            if 'sources' in comp:
                sources = comp['sources']
                if isinstance(sources, list):
                    source_paths.extend(sources)
            elif 'source' in comp:
                sources = comp['source']
                if isinstance(sources, str):
                    source_paths.append(sources)
                elif isinstance(sources, list):
                    source_paths.extend(sources)
            elif 'folder' in comp:
                warnings.append(
                    f"Component '{comp_name}' uses deprecated 'folder' field. "
                    "Consider migrating to 'source' or 'sources'."
                )
                source_paths.append(comp['folder'])

            for source_path in source_paths:
                abs_path = os.path.join(self.project_root, source_path)
                if not os.path.exists(abs_path):
                    errors.append(
                        f"Component '{comp_name}' source not found: {source_path} (absolute: {abs_path})"
                    )

        return errors, warnings

    def validate_source_paths(self, config: ForgeConfig) -> List[str]:
        """
        Validate that source paths exist in filesystem.

        Returns:
            List of warning messages (non-fatal issues)

        Raises:
            SourceNotFoundError: If critical source paths don't exist (includes all missing paths)
        """
        warnings = []
        errors = []

        # Validate common package sources
        for pkg in config.common_packages:
            if pkg.is_local_based:
                for source_path in pkg.source:
                    abs_path = os.path.join(self.project_root, source_path)
                    if not os.path.exists(abs_path):
                        errors.append(
                            f"Common package '{pkg.name}' source not found: {source_path} (absolute: {abs_path})"
                        )

        # Validate component sources
        for comp in config.components:
            source_paths = []

            if comp.sources:
                source_paths.extend(comp.sources)
            elif comp.source:
                source_paths.extend(comp.source if isinstance(comp.source, list) else [comp.source])
            elif comp.folder:
                warnings.append(
                    f"Component '{comp.name}' uses deprecated 'folder' field. "
                    "Consider migrating to 'source' or 'sources'."
                )
                source_paths.append(comp.folder)

            for source_path in source_paths:
                abs_path = os.path.join(self.project_root, source_path)
                if not os.path.exists(abs_path):
                    errors.append(
                        f"Component '{comp.name}' source not found: {source_path} (absolute: {abs_path})"
                    )

        # Raise all errors at once if any found
        if errors:
            raise SourceNotFoundError(
                "Source path validation failed",
                context={"errors": errors}
            )

        return warnings

    def validate_all(self, config_path: str) -> tuple[ForgeConfig, List[str]]:
        """
        Run all validation checks, collecting ALL errors before raising.

        Returns:
            Tuple of (validated_config, warnings)

        Raises:
            ConfigurationError: With all validation errors collected
        """
        import yaml
        from pydantic import ValidationError as PydanticValidationError

        all_errors = []
        warnings = []
        config = None

        # Load YAML first
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Failed to parse YAML: {e}")

        # Try to validate with Pydantic (collect errors)
        try:
            config = ForgeConfig(**data)
        except PydanticValidationError as e:
            # Extract all error messages from Pydantic validation
            for error in e.errors():
                loc = " -> ".join(str(l) for l in error['loc'])
                msg = error['msg']
                all_errors.append(f"{loc}: {msg}")

        # Always validate source paths (from raw data if Pydantic failed, or from config if it succeeded)
        if config:
            try:
                warnings = self.validate_source_paths(config)
            except SourceNotFoundError as e:
                # Collect source path errors
                if hasattr(e, 'context') and 'errors' in e.context:
                    all_errors.extend(e.context['errors'])
        else:
            # Pydantic failed, but we can still validate source paths from raw data
            source_errors, source_warnings = self.validate_source_paths_from_data(data)
            all_errors.extend(source_errors)
            warnings.extend(source_warnings)

        # If we collected any errors, raise them all
        if all_errors:
            raise ConfigurationError(
                "Configuration validation failed",
                context={"errors": all_errors}
            )

        return config, warnings
