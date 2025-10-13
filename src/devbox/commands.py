"""Command implementations using command pattern."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated, ClassVar, Literal

from pydantic import Field, SecretStr, TypeAdapter
from rich.panel import Panel
from rich.table import Table

from devbox.cloud_init import encode_cloud_init, load_cloud_init_template
from devbox.command_base import BaseCommand, BaseCommandConfig, CommandError
from devbox.config import ListResource
from lambdalabs import (
    Image,
    Instance,
    InstanceLaunchRequest,
    InstanceTerminateRequest,
    LambdaCloudClient,
)
from lambdalabs.models import ImageSpecificationID, InstanceStatus, PublicRegionCode


log = logging.getLogger(__name__)


def ssh_command(ip: str, username: str) -> str:
    """Generate SSH command string.

    Args:
        ip: Instance IP address
        username: SSH username

    Returns:
        SSH command string
    """
    return f"ssh {username}@{ip}"


# ============================================================================
# List Command
# ============================================================================


class ListCommand(BaseCommand):
    """List Lambda Cloud resources."""

    config: ListCommandConfig

    async def run(self) -> None:
        """Execute list command."""
        async with LambdaCloudClient(
            api_key=self.config.api.api_key,
            base_url=self.config.api.base_url,
        ) as client:
            match self.config.resource:
                case ListResource.instances:
                    instances = await client.list_instances()

                    if not instances:
                        self.console.print("[dim]No instances found[/dim]")
                        return

                    table = Table(title="Lambda Cloud Instances")
                    table.add_column("ID", style="cyan", no_wrap=True)
                    table.add_column("Status", style="magenta")
                    table.add_column("IP", style="green")
                    table.add_column("Region", style="blue")
                    table.add_column("Type", style="yellow")
                    table.add_column("Name", style="white")

                    for inst in instances:
                        status_style = {
                            InstanceStatus.active: "bold green",
                            InstanceStatus.booting: "bold yellow",
                            InstanceStatus.unhealthy: "bold red",
                            InstanceStatus.terminated: "dim",
                        }.get(inst.status, "")

                        table.add_row(
                            inst.id,
                            f"[{status_style}]{inst.status.value}[/{status_style}]",
                            inst.ip or "-",
                            inst.region.name.value,
                            inst.instance_type.name,
                            inst.name or "",
                        )

                    self.console.print(table)

                case ListResource.instance_types:
                    data = await client.list_instance_types()

                    # Filter by availability if requested
                    items_list = list(data.root.items())
                    if self.config.available_only:
                        items_list = [
                            (name, item)
                            for name, item in items_list
                            if item.regions_with_capacity_available
                        ]

                    # Sort by availability first, then price
                    sorted_items = sorted(
                        items_list,
                        key=lambda x: (
                            len(x[1].regions_with_capacity_available) == 0,
                            -x[1].instance_type.price_cents_per_hour,
                            x[0],
                        ),
                    )

                    # Display each instance type with all information
                    for _name, item in sorted_items:
                        it = item.instance_type
                        specs = it.specs

                        # Create a table for this instance type
                        table = Table(
                            show_header=False,
                            box=None,
                            padding=(0, 1),
                            expand=False,
                        )
                        table.add_column(style="dim", justify="right", no_wrap=True)
                        table.add_column(style="white")

                        # Format price
                        price_dollars = it.price_cents_per_hour / 100

                        # Format regions
                        if item.regions_with_capacity_available:
                            regions_list = [
                                r.name.value
                                for r in item.regions_with_capacity_available
                            ]
                            regions_display = (
                                f"[green]✓[/green] {', '.join(regions_list)}"
                            )
                        else:
                            regions_display = "[dim]None[/dim]"

                        # Header with instance name
                        self.console.print(
                            f"\n[bold cyan]{it.name}[/bold cyan] - {it.description}"
                        )

                        # Add all details
                        table.add_row("GPU Type:", it.gpu_description)
                        table.add_row(
                            "GPUs:",
                            str(specs.gpus) if specs.gpus > 0 else "0 (CPU only)",
                        )
                        table.add_row("vCPUs:", str(specs.vcpus))
                        table.add_row("RAM:", f"{specs.memory_gib} GiB")
                        table.add_row("Storage:", f"{specs.storage_gib} GiB")
                        table.add_row(
                            "Price:",
                            f"${price_dollars:.2f}/hour (${price_dollars * 24:.2f}/day, ${price_dollars * 730:.2f}/month)",
                        )
                        table.add_row("Available:", regions_display)

                        self.console.print(table)

                    # Show summary
                    available_count = sum(
                        1
                        for item in data.root.values()
                        if item.regions_with_capacity_available
                    )
                    self.console.print(
                        f"\n[bold]{available_count}[/bold] of {len(data.root)} instance types have capacity available"
                    )

                case ListResource.images:
                    images = await client.list_images()

                    # Get available regions if filtering is enabled
                    available_regions: set[str] = set()
                    if self.config.available_only:
                        instance_types_data = await client.list_instance_types()
                        for item in instance_types_data.root.values():
                            if item.regions_with_capacity_available:
                                for region in item.regions_with_capacity_available:
                                    available_regions.add(region.name.value)

                    # Filter images by available regions if requested
                    if self.config.available_only:
                        images = [
                            img
                            for img in images
                            if img.region.name.value in available_regions
                        ]

                    if not images:
                        self.console.print("[dim]No images found[/dim]")
                        return

                    # Group images by (family, description, version, architecture)
                    from collections import defaultdict

                    by_image_group: dict[tuple[str, str, str, str], list[Image]] = (
                        defaultdict(list)
                    )
                    for img in images:
                        key = (
                            img.family,
                            img.description,
                            img.version,
                            img.architecture.value,
                        )
                        by_image_group[key].append(img)

                    # Sort groups
                    sorted_groups: list[tuple[str, str, str, str]] = sorted(
                        by_image_group.keys()
                    )

                    # Display each image group
                    for family, description, version, architecture in sorted_groups:
                        group_images: list[Image] = by_image_group[
                            (family, description, version, architecture)
                        ]

                        # Filter regional variants by available regions if requested
                        if self.config.available_only and available_regions:
                            group_images = [
                                img
                                for img in group_images
                                if img.region.name.value in available_regions
                            ]

                        # Skip empty groups after filtering
                        if not group_images:
                            continue

                        # Get name from first image (should be same across all in group)
                        first = group_images[0]

                        self.console.print(f"\n[bold cyan]{first.name}[/bold cyan]")
                        self.console.print(f"[dim]Description:[/dim] {description}")
                        self.console.print(f"[dim]Family:[/dim] {family}")
                        self.console.print(f"[dim]Version:[/dim] {version}")
                        self.console.print(f"[dim]Architecture:[/dim] {architecture}")

                        # Create table for regional variants
                        table = Table(show_header=True, box=None, padding=(0, 1))
                        table.add_column("ID", style="yellow", no_wrap=True)
                        table.add_column("Region", style="cyan")
                        table.add_column("Created", style="dim")
                        table.add_column("Updated", style="dim")

                        # Sort by region name
                        group_images.sort(key=lambda x: x.region.name.value)

                        for img in group_images:
                            table.add_row(
                                img.id,
                                img.region.name.value,
                                img.created_time.strftime("%Y-%m-%d"),
                                img.updated_time.strftime("%Y-%m-%d"),
                            )

                        self.console.print(table)

                    # Show summary
                    total_variants = sum(
                        len(group) for group in by_image_group.values()
                    )
                    if self.config.available_only and available_regions:
                        self.console.print(
                            f"\n[bold]{len(by_image_group)}[/bold] unique images with {total_variants} regional variants "
                            f"(filtered to {len(available_regions)} regions with available instances)"
                        )
                    else:
                        self.console.print(
                            f"\n[bold]{len(by_image_group)}[/bold] unique images with {total_variants} total regional variants"
                        )

                case ListResource.filesystems:
                    filesystems = await client.list_filesystems()

                    # Get available regions if filtering is enabled
                    available_regions = set()
                    if self.config.available_only:
                        instance_types_data = await client.list_instance_types()
                        for item in instance_types_data.root.values():
                            if item.regions_with_capacity_available:
                                for region in item.regions_with_capacity_available:
                                    available_regions.add(region.name.value)

                    # Filter filesystems by available regions if requested
                    if self.config.available_only and available_regions:
                        filesystems = [
                            fs
                            for fs in filesystems
                            if fs.region.name.value in available_regions
                        ]

                    if not filesystems:
                        self.console.print("[dim]No filesystems found[/dim]")
                        return

                    # Display each filesystem
                    for fs in filesystems:
                        # Format size
                        if fs.bytes_used is not None:
                            size_gb = fs.bytes_used / (1024**3)
                            if size_gb < 1:
                                size_mb = fs.bytes_used / (1024**2)
                                size_display = f"{size_mb:.1f} MB"
                            else:
                                size_display = f"{size_gb:.1f} GB"
                        else:
                            size_display = "Unknown"

                        # Format in use status
                        in_use_display = (
                            "[green]In use[/green]"
                            if fs.is_in_use
                            else "[dim]Not in use[/dim]"
                        )

                        # Create table for this filesystem
                        table = Table(
                            show_header=False,
                            box=None,
                            padding=(0, 1),
                            expand=False,
                        )
                        table.add_column(style="dim", justify="right", no_wrap=True)
                        table.add_column(style="white")

                        self.console.print(f"\n[bold cyan]{fs.name}[/bold cyan]")
                        table.add_row("ID:", fs.id)
                        table.add_row("Region:", fs.region.name.value)
                        table.add_row("Mount Point:", fs.mount_point)
                        table.add_row("Status:", in_use_display)
                        table.add_row("Size:", size_display)
                        table.add_row(
                            "Created:", fs.created.strftime("%Y-%m-%d %H:%M:%S")
                        )
                        table.add_row("Created By:", fs.created_by.email)

                        self.console.print(table)

                    # Show summary
                    if self.config.available_only and available_regions:
                        self.console.print(
                            f"\n[bold]{len(filesystems)}[/bold] filesystems "
                            f"(filtered to {len(available_regions)} regions with available instances)"
                        )
                    else:
                        self.console.print(
                            f"\n[bold]{len(filesystems)}[/bold] total filesystems"
                        )

                case ListResource.ssh_keys:
                    ssh_keys = await client.list_ssh_keys()

                    if not ssh_keys:
                        self.console.print("[dim]No SSH keys found[/dim]")
                        return

                    # Display each SSH key
                    for ssh_key in ssh_keys:
                        # Create table for this key
                        table = Table(
                            show_header=False,
                            box=None,
                            padding=(0, 1),
                            expand=False,
                        )
                        table.add_column(style="dim", justify="right", no_wrap=True)
                        table.add_column(style="white")

                        self.console.print(f"\n[bold cyan]{ssh_key.name}[/bold cyan]")
                        table.add_row("ID:", ssh_key.id)
                        table.add_row("Public Key:", ssh_key.public_key)

                        self.console.print(table)

                    # Show summary
                    self.console.print(f"\n[bold]{len(ssh_keys)}[/bold] SSH keys")

                case ListResource.firewall_rulesets:
                    rulesets = await client.list_firewall_rulesets()

                    # Get available regions if filtering is enabled
                    available_regions = set()
                    if self.config.available_only:
                        instance_types_data = await client.list_instance_types()
                        for item in instance_types_data.root.values():
                            if item.regions_with_capacity_available:
                                for region in item.regions_with_capacity_available:
                                    available_regions.add(region.name.value)

                    # Filter rulesets by available regions if requested
                    if self.config.available_only and available_regions:
                        rulesets = [
                            rs
                            for rs in rulesets
                            if rs.region.name.value in available_regions
                        ]

                    if not rulesets:
                        self.console.print("[dim]No firewall rulesets found[/dim]")
                        return

                    # Display each firewall ruleset
                    for ruleset in rulesets:
                        # Format in use status
                        if ruleset.instance_ids:
                            in_use_display = f"[green]In use[/green] ({len(ruleset.instance_ids)} instances)"
                        else:
                            in_use_display = "[dim]Not in use[/dim]"

                        # Create table for this ruleset
                        table = Table(
                            show_header=False,
                            box=None,
                            padding=(0, 1),
                            expand=False,
                        )
                        table.add_column(style="dim", justify="right", no_wrap=True)
                        table.add_column(style="white")

                        self.console.print(f"\n[bold cyan]{ruleset.name}[/bold cyan]")
                        table.add_row("ID:", ruleset.id)
                        table.add_row("Region:", ruleset.region.name.value)
                        table.add_row("Status:", in_use_display)
                        table.add_row(
                            "Created:", ruleset.created.strftime("%Y-%m-%d %H:%M:%S")
                        )
                        table.add_row("Rules:", f"{len(ruleset.rules)} rule(s)")

                        self.console.print(table)

                        # Display rules if any
                        if ruleset.rules:
                            rules_table = Table(
                                show_header=True,
                                box=None,
                                padding=(0, 1),
                                expand=False,
                            )
                            rules_table.add_column("Protocol", style="cyan")
                            rules_table.add_column("Ports", style="yellow")
                            rules_table.add_column("Source", style="green")
                            rules_table.add_column("Description", style="white")

                            for rule in ruleset.rules:
                                # Format port range
                                if rule.port_range:
                                    if (
                                        rule.port_range[0].root
                                        == rule.port_range[1].root
                                    ):
                                        ports = str(rule.port_range[0].root)
                                    else:
                                        ports = f"{rule.port_range[0].root}-{rule.port_range[1].root}"
                                else:
                                    ports = "-"

                                rules_table.add_row(
                                    rule.protocol.value,
                                    ports,
                                    rule.source_network,
                                    rule.description,
                                )

                            self.console.print(rules_table)

                    # Show summary
                    if self.config.available_only and available_regions:
                        self.console.print(
                            f"\n[bold]{len(rulesets)}[/bold] firewall rulesets "
                            f"(filtered to {len(available_regions)} regions with available instances)"
                        )
                    else:
                        self.console.print(
                            f"\n[bold]{len(rulesets)}[/bold] total firewall rulesets"
                        )

                case _:
                    raise CommandError(f"Unknown resource: {self.config.resource}")


class ListCommandConfig(BaseCommandConfig):
    """Configuration for list command."""

    command: Literal["list"] = "list"
    resource: ListResource = Field(description="Resource type to list")
    available_only: bool = Field(
        description="Show only instance types with available capacity (for instance-types resource)"
    )

    _command_class: ClassVar[type[BaseCommand]] = ListCommand


# ============================================================================
# Up Command
# ============================================================================


class UpCommand(BaseCommand):
    """Launch instances with cloud-init configuration."""

    config: UpCommandConfig

    async def run(self) -> None:
        """Execute up command."""
        # Build Jinja2 context for cloud-init template
        context = self._build_cloud_init_context()

        # Load and render cloud-init template
        cloud_init_yaml = load_cloud_init_template(context)
        cloud_init_b64 = encode_cloud_init(cloud_init_yaml)

        # Prepare launch request
        request = InstanceLaunchRequest(
            region_name=PublicRegionCode(self.config.region),
            instance_type_name=self.config.instance_type,
            ssh_key_names=[self.config.ssh_key_name],
            file_system_names=(
                [self.config.filesystem_name] if self.config.filesystem_name else None
            ),
            name=self.config.instance_name,
            image=(
                ImageSpecificationID(id=self.config.image_id)
                if self.config.image_id
                else None
            ),
            user_data=SecretStr(cloud_init_b64) if cloud_init_b64 else None,
        )

        async with LambdaCloudClient(
            api_key=self.config.api.api_key,
            base_url=self.config.api.base_url,
        ) as client:
            # Launch instances
            with self.console.status(
                f"[bold green]Launching {self.config.quantity} instance(s)..."
            ):
                response = await client.launch_instance(request)

            if not response.instance_ids:
                log.warning("Launch returned no instance IDs")
                self.console.print("[yellow]⚠[/yellow] Launch returned no instance IDs")
                return

            instance_ids = response.instance_ids
            for instance_id in instance_ids:
                self.console.print(
                    f"[green]✓[/green] Launched: [cyan]{instance_id}[/cyan]"
                )

            # Wait for instances if requested
            if self.config.wait_after_launch:
                ready_instances = await self._wait_for_instances(client, instance_ids)

                # Display rich summary
                self._display_launch_summary(ready_instances)

    def _build_cloud_init_context(self) -> dict[str, str | None]:
        """Build Jinja2 context for cloud-init template rendering.

        Returns:
            Dictionary of template variables
        """
        filesystem_mount = None
        if self.config.filesystem_name:
            # Lambda standard mount point pattern
            filesystem_mount = f"/lambda/nfs/{self.config.filesystem_name}"

        return {
            "filesystem_name": self.config.filesystem_name,
            "filesystem_mount": filesystem_mount,
            "ssh_username": self.config.ssh.username,
        }

    async def _wait_for_instances(
        self, client: LambdaCloudClient, instance_ids: list[str]
    ) -> list[Instance]:
        """Wait for multiple instances to be ready with progressive feedback.

        Args:
            client: Lambda Cloud API client
            instance_ids: List of instance IDs to wait for

        Returns:
            List of ready instances

        Raises:
            TimeoutError: If instances not ready within timeout
        """
        deadline = time.time() + self.config.wait.timeout
        ready: dict[str, Instance] = {}
        backoff = self.config.wait.poll_interval

        self.console.print(
            f"\n[bold cyan]Waiting for {len(instance_ids)} instance(s) to be ready...[/bold cyan]"
        )

        while len(ready) < len(instance_ids):
            if time.time() > deadline:
                missing = [iid for iid in instance_ids if iid not in ready]
                raise TimeoutError(
                    f"Instances not ready within {self.config.wait.timeout}s: {missing}"
                )

            instances = await client.list_instances()

            for iid in instance_ids:
                if iid in ready:
                    continue

                match = next((i for i in instances if i.id == iid), None)
                if (
                    match
                    and match.ip
                    and match.status in {InstanceStatus.booting, InstanceStatus.active}
                ):
                    ready[iid] = match
                    self.console.print(
                        f"[green]✓[/green] Ready: [cyan]{match.id}[/cyan] "
                        f"→ [green]{match.ip}[/green] ([magenta]{match.status.value}[/magenta])"
                    )

            if len(ready) < len(instance_ids):
                await asyncio.sleep(backoff)
                # Exponential backoff up to 15s
                backoff = min(backoff * 1.5, 15.0)

        return list(ready.values())

    def _display_launch_summary(self, instances: list[Instance]) -> None:
        """Display rich summary of launched instances.

        Args:
            instances: List of ready instances
        """
        self.console.print("\n" + "=" * 60)
        self.console.print("[bold green]Launch Complete![/bold green]\n")

        # Create table
        table = Table(title="Launched Instances")
        table.add_column("Instance ID", style="cyan", no_wrap=True)
        table.add_column("IP Address", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("SSH Command", style="white")

        for inst in instances:
            ssh_cmd = ssh_command(inst.ip or "", username=self.config.ssh.username)
            table.add_row(
                inst.id,
                inst.ip or "-",
                inst.status.value,
                ssh_cmd,
            )

        self.console.print(table)

        # Show mount info if filesystem attached
        if self.config.filesystem_name:
            self.console.print(
                f"\n[bold]Persistent Storage:[/bold] /lambda/nfs/{self.config.filesystem_name}"
            )
            self.console.print("  • [cyan]/nix[/cyan] → Nix store")
            self.console.print("  • [cyan]/home[/cyan] → User home directories")

        self.console.print("\n" + "=" * 60)


class UpCommandConfig(BaseCommandConfig):
    """Configuration for up (launch) command."""

    command: Literal["up"] = "up"
    region: str = Field(description="Lambda Cloud region")
    instance_type: str = Field(description="Instance type name")
    ssh_key_name: str = Field(description="SSH key name")
    filesystem_name: str | None = Field(description="Filesystem name to attach")
    instance_name: str | None = Field(description="Instance name")
    image_id: str | None = Field(description="Image ID to use")
    quantity: int = Field(description="Number of instances", ge=1)
    wait_after_launch: bool = Field(description="Wait for instance to be ready")

    _command_class: ClassVar[type[BaseCommand]] = UpCommand


# ============================================================================
# Wait Command
# ============================================================================


class WaitCommand(BaseCommand):
    """Wait for an instance to be ready."""

    config: WaitCommandConfig

    async def run(self) -> None:
        """Execute wait command."""
        async with LambdaCloudClient(
            api_key=self.config.api.api_key,
            base_url=self.config.api.base_url,
        ) as client:
            inst = await self._wait_for_instance(client, self.config.instance_id)
            self.console.print(
                f"[green]✓[/green] Ready: [cyan]{inst.id}[/cyan] "
                f"[green]{inst.ip}[/green] ([magenta]{inst.status.value}[/magenta])"
            )
            self.console.print(
                Panel(
                    ssh_command(inst.ip or "", username=self.config.ssh.username),
                    title="SSH Command",
                    border_style="green",
                )
            )

    async def _wait_for_instance(
        self, client: LambdaCloudClient, instance_id: str
    ) -> Instance:
        """Wait for instance to be ready."""
        deadline = time.time() + self.config.wait.timeout
        with self.console.status(
            f"[bold cyan]Waiting for instance {instance_id} to be ready..."
        ):
            while time.time() < deadline:
                instances = await client.list_instances()
                match = next((i for i in instances if i.id == instance_id), None)
                if (
                    match
                    and match.ip
                    and match.status in {InstanceStatus.booting, InstanceStatus.active}
                ):
                    return match
                await asyncio.sleep(self.config.wait.poll_interval)
        raise TimeoutError(
            f"Instance {instance_id} not ready within {self.config.wait.timeout}s"
        )


class WaitCommandConfig(BaseCommandConfig):
    """Configuration for wait command."""

    command: Literal["wait"] = "wait"
    instance_id: str = Field(description="Instance ID to wait for")

    _command_class: ClassVar[type[BaseCommand]] = WaitCommand


# ============================================================================
# Down Command
# ============================================================================


class DownCommand(BaseCommand):
    """Terminate an instance."""

    config: DownCommandConfig

    async def run(self) -> None:
        """Execute down command."""
        request = InstanceTerminateRequest(
            instance_ids=[self.config.instance_id],
        )

        async with LambdaCloudClient(
            api_key=self.config.api.api_key,
            base_url=self.config.api.base_url,
        ) as client:
            with self.console.status(
                f"[bold red]Terminating instance {self.config.instance_id}..."
            ):
                response = await client.terminate_instances(request)

            self.console.print(
                f"[green]✓[/green] Instance [cyan]{self.config.instance_id}[/cyan] terminated"
            )
            self.console.print_json(data=response.model_dump(mode="json"))


class DownCommandConfig(BaseCommandConfig):
    """Configuration for down (terminate) command."""

    command: Literal["down"] = "down"
    instance_id: str = Field(description="Instance ID to terminate")

    _command_class: ClassVar[type[BaseCommand]] = DownCommand


# ============================================================================
# SSH Command
# ============================================================================


class SshCommand(BaseCommand):
    """Get SSH command for an instance."""

    config: SshCommandConfig

    async def run(self) -> None:
        """Execute ssh command."""
        async with LambdaCloudClient(
            api_key=self.config.api.api_key,
            base_url=self.config.api.base_url,
        ) as client:
            with self.console.status(
                f"[bold cyan]Fetching instance {self.config.instance_id}..."
            ):
                instances = await client.list_instances()

            match = next(
                (i for i in instances if i.id == self.config.instance_id), None
            )

            if not match:
                raise CommandError(f"Instance not found: {self.config.instance_id}")

            if not match.ip:
                raise CommandError(
                    f"Instance {self.config.instance_id} has no IP address yet"
                )

            self.console.print(
                Panel(
                    ssh_command(match.ip, username=self.config.ssh.username),
                    title=f"SSH Command for {self.config.instance_id}",
                    border_style="cyan",
                )
            )


class SshCommandConfig(BaseCommandConfig):
    """Configuration for ssh command."""

    command: Literal["ssh"] = "ssh"
    instance_id: str = Field(description="Instance ID")

    _command_class: ClassVar[type[BaseCommand]] = SshCommand


# ============================================================================
# Discriminated Union
# ============================================================================

CommandConfig = Annotated[
    ListCommandConfig
    | UpCommandConfig
    | WaitCommandConfig
    | DownCommandConfig
    | SshCommandConfig,
    Field(discriminator="command"),
]

# Type adapter for validation
command_adapter: TypeAdapter[CommandConfig] = TypeAdapter(CommandConfig)
