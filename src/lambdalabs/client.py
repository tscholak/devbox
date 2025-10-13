"""Lambda Labs Cloud API async client."""

from __future__ import annotations

from typing import Any

import aiohttp

from lambdalabs.models import (
    Filesystem,
    FirewallRuleset,
    Image,
    Instance,
    InstanceLaunchRequest,
    InstanceLaunchResponse,
    InstanceModificationRequest,
    InstanceRestartRequest,
    InstanceRestartResponse,
    InstanceTerminateRequest,
    InstanceTerminateResponse,
    InstanceTypes,
    SSHKey,
)


class ApiError(Exception):
    """Lambda Cloud API error."""

    pass


class LambdaCloudClient:
    """Async Lambda Cloud API client.

    Example:
        async with LambdaCloudClient(api_key="sk_xxx") as client:
            instances = await client.list_instances()
            for instance in instances:
                print(instance.id, instance.status)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://cloud.lambda.ai/api/v1",
        *,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        """Initialize client.

        Args:
            api_key: Lambda Cloud API key
            base_url: API base URL
            timeout: Optional custom timeout configuration
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or aiohttp.ClientTimeout(total=120)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> LambdaCloudClient:
        """Enter async context."""
        auth = aiohttp.BasicAuth(self.api_key, "")
        self._session = aiohttp.ClientSession(auth=auth, timeout=self.timeout)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        """Exit async context."""
        if self._session:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request.

        Args:
            method: HTTP method
            path: API endpoint path
            json: Optional JSON request body

        Returns:
            JSON response data

        Raises:
            ApiError: If request fails
        """
        assert self._session is not None, "Client must be used as async context manager"

        url = f"{self.base_url}{path}"
        headers = {"accept": "application/json"}

        if json is not None:
            headers["content-type"] = "application/json"

        async with self._session.request(
            method, url, headers=headers, json=json
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise ApiError(f"{method} {path} -> {resp.status}: {text}")

            data: dict[str, Any] = await resp.json()
            return data

    # Instance operations

    async def list_instances(self) -> list[Instance]:
        """List all instances.

        Returns:
            List of Instance objects
        """
        data = await self._request("GET", "/instances")
        items = data.get("data", [])
        return [Instance.model_validate(item) for item in items]

    async def get_instance(self, instance_id: str) -> Instance:
        """Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance object
        """
        data = await self._request("GET", f"/instances/{instance_id}")
        return Instance.model_validate(data.get("data"))

    async def launch_instance(
        self,
        request: InstanceLaunchRequest,
    ) -> InstanceLaunchResponse:
        """Launch instance(s).

        Args:
            request: Launch instance request

        Returns:
            Launch response with instance IDs
        """
        payload = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._request("POST", "/instance-operations/launch", json=payload)
        return InstanceLaunchResponse.model_validate(data.get("data", data))

    async def terminate_instances(
        self,
        request: InstanceTerminateRequest,
    ) -> InstanceTerminateResponse:
        """Terminate instances.

        Args:
            request: Terminate instances request

        Returns:
            Terminate response
        """
        payload = request.model_dump(by_alias=True, mode="json")
        data = await self._request(
            "POST", "/instance-operations/terminate", json=payload
        )
        return InstanceTerminateResponse.model_validate(data.get("data", data))

    async def restart_instances(
        self,
        request: InstanceRestartRequest,
    ) -> InstanceRestartResponse:
        """Restart instances.

        Args:
            request: Restart instances request

        Returns:
            Restart response
        """
        payload = request.model_dump(by_alias=True, mode="json")
        data = await self._request("POST", "/instance-operations/restart", json=payload)
        return InstanceRestartResponse.model_validate(data.get("data", data))

    async def modify_instance(
        self,
        instance_id: str,
        request: InstanceModificationRequest,
    ) -> Instance:
        """Modify instance.

        Args:
            instance_id: Instance ID
            request: Modification request

        Returns:
            Updated instance
        """
        payload = request.model_dump(exclude_none=True, by_alias=True, mode="json")
        data = await self._request("PATCH", f"/instances/{instance_id}", json=payload)
        return Instance.model_validate(data.get("data"))

    # Instance types

    async def list_instance_types(self) -> InstanceTypes:
        """List available instance types.

        Returns:
            Instance types with availability
        """
        data = await self._request("GET", "/instance-types")
        return InstanceTypes.model_validate(data.get("data", data))

    # SSH keys

    async def list_ssh_keys(self) -> list[SSHKey]:
        """List SSH keys.

        Returns:
            List of SSH keys
        """
        data = await self._request("GET", "/ssh-keys")
        items = data.get("data", [])
        return [SSHKey.model_validate(item) for item in items]

    # Filesystems

    async def list_filesystems(self) -> list[Filesystem]:
        """List filesystems.

        Returns:
            List of filesystems
        """
        data = await self._request("GET", "/file-systems")
        items = data.get("data", [])
        return [Filesystem.model_validate(item) for item in items]

    # Images

    async def list_images(self) -> list[Image]:
        """List available images.

        Returns:
            List of images
        """
        data = await self._request("GET", "/images")
        items = data.get("data", [])
        return [Image.model_validate(item) for item in items]

    # Firewall rulesets

    async def list_firewall_rulesets(self) -> list[FirewallRuleset]:
        """List firewall rulesets.

        Returns:
            List of firewall rulesets
        """
        data = await self._request("GET", "/firewall-rulesets")
        items = data.get("data", [])
        return [FirewallRuleset.model_validate(item) for item in items]
