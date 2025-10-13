"""Global configuration models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ListResource(str, Enum):
    """Resource types that can be listed."""

    instances = "instances"
    instance_types = "instance-types"
    images = "images"
    filesystems = "filesystems"
    ssh_keys = "ssh-keys"
    firewall_rulesets = "firewall-rulesets"


class ApiConfig(BaseModel):
    """Lambda Cloud API configuration."""

    base_url: str = Field(
        description="Base URL for Lambda Cloud API",
    )
    api_key: str = Field(
        description="API key for Lambda Cloud",
    )
    timeout: int = Field(
        description="API request timeout in seconds",
        gt=0,
    )


class WaitConfig(BaseModel):
    """Wait operation configuration."""

    timeout: int = Field(
        description="Wait timeout in seconds",
        gt=0,
    )
    poll_interval: float = Field(
        description="Polling interval in seconds",
        gt=0,
    )


class SshConfig(BaseModel):
    """SSH configuration."""

    username: str = Field(
        description="Default SSH username",
    )
