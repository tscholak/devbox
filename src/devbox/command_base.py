"""Base classes for command pattern implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field
from rich.console import Console

from devbox.config import ApiConfig, SshConfig, WaitConfig


class CommandError(Exception):
    """Command execution error."""

    pass


class BaseCommand(ABC):
    """Base class for commands."""

    def __init__(
        self, config: BaseCommandConfig, console: Console | None = None
    ) -> None:
        """Initialize command.

        Args:
            config: Full configuration (includes command-specific fields)
            console: Rich console for output (creates default if None)
        """
        self.config = config
        self.console = console or Console()

    @abstractmethod
    async def run(self) -> None:
        """Execute the command.

        Raises:
            CommandError: If command execution fails
        """
        ...


class BaseCommandConfig(BaseModel, ABC):
    """Base configuration for all commands.

    This serves as the root config. All global configs are here,
    and command-specific fields are added in subclasses.
    """

    # Global configurations (available to all commands)
    api: ApiConfig = Field(description="API configuration")
    ssh: SshConfig = Field(description="SSH configuration")
    wait: WaitConfig = Field(description="Wait operation configuration")

    # Command class binding
    _command_class: ClassVar[type[BaseCommand]]

    def create_command(self) -> BaseCommand:
        """Create command instance from this config.

        Returns:
            Command instance with full config
        """
        return self._command_class(config=self)
