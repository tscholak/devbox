"""Lambda Labs Cloud API async client."""

from __future__ import annotations

import json
from typing import Annotated, Any, TypeVar

import aiohttp
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from lambdalabs.models import (
    ApiErrorAccountInactive,
    ApiErrorDuplicate,
    ApiErrorFilesystemInUse,
    ApiErrorFileSystemInWrongRegion,
    ApiErrorFilesystemNotFound,
    ApiErrorFirewallRulesetInUse,
    ApiErrorFirewallRulesetNotFound,
    ApiErrorInstanceNotFound,
    ApiErrorInsufficientCapacity,
    ApiErrorInternal,
    ApiErrorInvalidBillingAddress,
    ApiErrorInvalidParameters,
    ApiErrorLaunchResourceNotFound,
    ApiErrorQuotaExceeded,
    ApiErrorUnauthorized,
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


T = TypeVar("T")

# Context-specific error unions for different API endpoints
# These use the same error codes but in different contexts

# Common errors that can occur on any endpoint
CommonApiError = Annotated[
    ApiErrorUnauthorized | ApiErrorAccountInactive | ApiErrorInternal,
    Field(discriminator="code"),
]

# Instance launch errors
InstanceLaunchError = Annotated[
    ApiErrorUnauthorized
    | ApiErrorAccountInactive
    | ApiErrorLaunchResourceNotFound
    | ApiErrorInvalidParameters
    | ApiErrorInvalidBillingAddress
    | ApiErrorFileSystemInWrongRegion
    | ApiErrorInsufficientCapacity
    | ApiErrorQuotaExceeded
    | ApiErrorInternal,
    Field(discriminator="code"),
]

# Instance operation errors (get, terminate, restart, modify)
InstanceOperationError = Annotated[
    ApiErrorUnauthorized
    | ApiErrorAccountInactive
    | ApiErrorInstanceNotFound
    | ApiErrorInvalidParameters
    | ApiErrorInternal,
    Field(discriminator="code"),
]

# Filesystem errors
FilesystemError = Annotated[
    ApiErrorUnauthorized
    | ApiErrorAccountInactive
    | ApiErrorFilesystemNotFound
    | ApiErrorFilesystemInUse
    | ApiErrorDuplicate
    | ApiErrorInternal,
    Field(discriminator="code"),
]

# Firewall ruleset errors
FirewallRulesetError = Annotated[
    ApiErrorUnauthorized
    | ApiErrorAccountInactive
    | ApiErrorFirewallRulesetNotFound
    | ApiErrorFirewallRulesetInUse
    | ApiErrorDuplicate
    | ApiErrorInternal,
    Field(discriminator="code"),
]

# Type adapters for error contexts
instance_launch_error_adapter = TypeAdapter(InstanceLaunchError)
instance_operation_error_adapter = TypeAdapter(InstanceOperationError)
filesystem_error_adapter = TypeAdapter(FilesystemError)
firewall_ruleset_error_adapter = TypeAdapter(FirewallRulesetError)
common_error_adapter = TypeAdapter(CommonApiError)

# Type adapters for response data
instance_list_adapter = TypeAdapter(list[Instance])
instance_adapter = TypeAdapter(Instance)
instance_launch_response_adapter = TypeAdapter(InstanceLaunchResponse)
instance_terminate_response_adapter = TypeAdapter(InstanceTerminateResponse)
instance_restart_response_adapter = TypeAdapter(InstanceRestartResponse)
instance_types_adapter = TypeAdapter(InstanceTypes)
ssh_key_list_adapter = TypeAdapter(list[SSHKey])
filesystem_list_adapter = TypeAdapter(list[Filesystem])
image_list_adapter = TypeAdapter(list[Image])
firewall_ruleset_list_adapter = TypeAdapter(list[FirewallRuleset])


class ApiError(Exception):
    """Lambda Cloud API error with structured error details.

    Attributes:
        status: HTTP status code
        method: HTTP method
        path: API endpoint path
        error: Parsed error model (code, message, suggestion)
        raw_text: Raw response text
    """

    def __init__(
        self,
        status: int,
        method: str,
        path: str,
        error: (
            InstanceLaunchError
            | InstanceOperationError
            | FilesystemError
            | FirewallRulesetError
            | CommonApiError
            | None
        ) = None,
        raw_text: str | None = None,
    ):
        self.status = status
        self.method = method
        self.path = path
        self.error = error
        self.raw_text = raw_text

        # Build human-readable message
        parts = [f"{method} {path} -> {status}"]
        if error:
            parts.append(f"[{error.code}] {error.message}")
        elif raw_text:
            parts.append(raw_text[:200])  # Truncate long errors

        super().__init__(": ".join(parts))


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
        response_adapter: TypeAdapter[T],
        error_adapter: TypeAdapter[Any],
        *,
        body: BaseModel | None = None,
    ) -> T:
        """Make an API request with full Pydantic parsing.

        Args:
            method: HTTP method
            path: API endpoint path
            response_adapter: TypeAdapter for parsing successful response data
            error_adapter: TypeAdapter for parsing error responses
            body: Optional Pydantic model for request body

        Returns:
            Parsed response data

        Raises:
            ApiError: If request fails with parsed error details
        """
        assert self._session is not None, "Client must be used as async context manager"

        url = f"{self.base_url}{path}"
        headers = {"accept": "application/json"}

        request_json = None
        if body is not None:
            headers["content-type"] = "application/json"
            request_json = body.model_dump(
                exclude_none=True, by_alias=True, mode="json"
            )

        async with self._session.request(
            method, url, headers=headers, json=request_json
        ) as resp:
            text = await resp.text()

            if resp.status >= 400:
                # Try to parse structured error response
                parsed_error = None
                try:
                    error_data = json.loads(text) if text else {}
                    if "error" in error_data:
                        parsed_error = error_adapter.validate_python(
                            error_data["error"]
                        )
                except (json.JSONDecodeError, ValidationError):
                    # Failed to parse structured error, fall back to raw text
                    pass

                raise ApiError(
                    status=resp.status,
                    method=method,
                    path=path,
                    error=parsed_error,
                    raw_text=text if not parsed_error else None,
                )

            # Parse successful response
            try:
                response_data = json.loads(text) if text else {}
                # Most endpoints wrap data in {"data": ...}
                if "data" in response_data:
                    return response_adapter.validate_python(response_data["data"])
                return response_adapter.validate_python(response_data)
            except (json.JSONDecodeError, ValidationError) as e:
                # Response parsing failed - raise as ApiError for consistency
                raise ApiError(
                    status=resp.status,
                    method=method,
                    path=path,
                    raw_text=f"Failed to parse response: {e}\n{text[:200]}",
                ) from None

    # Instance operations

    async def list_instances(self) -> list[Instance]:
        """List all instances.

        Returns:
            List of Instance objects
        """
        return await self._request(
            "GET",
            "/instances",
            instance_list_adapter,
            common_error_adapter,
        )

    async def get_instance(self, instance_id: str) -> Instance:
        """Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance object
        """
        return await self._request(
            "GET",
            f"/instances/{instance_id}",
            instance_adapter,
            instance_operation_error_adapter,
        )

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
        return await self._request(
            "POST",
            "/instance-operations/launch",
            instance_launch_response_adapter,
            instance_launch_error_adapter,
            body=request,
        )

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
        return await self._request(
            "POST",
            "/instance-operations/terminate",
            instance_terminate_response_adapter,
            instance_operation_error_adapter,
            body=request,
        )

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
        return await self._request(
            "POST",
            "/instance-operations/restart",
            instance_restart_response_adapter,
            instance_operation_error_adapter,
            body=request,
        )

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
        return await self._request(
            "PATCH",
            f"/instances/{instance_id}",
            instance_adapter,
            instance_operation_error_adapter,
            body=request,
        )

    # Instance types

    async def list_instance_types(self) -> InstanceTypes:
        """List available instance types.

        Returns:
            Instance types with availability
        """
        return await self._request(
            "GET",
            "/instance-types",
            instance_types_adapter,
            common_error_adapter,
        )

    # SSH keys

    async def list_ssh_keys(self) -> list[SSHKey]:
        """List SSH keys.

        Returns:
            List of SSH keys
        """
        return await self._request(
            "GET",
            "/ssh-keys",
            ssh_key_list_adapter,
            common_error_adapter,
        )

    # Filesystems

    async def list_filesystems(self) -> list[Filesystem]:
        """List filesystems.

        Returns:
            List of filesystems
        """
        return await self._request(
            "GET",
            "/file-systems",
            filesystem_list_adapter,
            filesystem_error_adapter,
        )

    # Images

    async def list_images(self) -> list[Image]:
        """List available images.

        Returns:
            List of images
        """
        return await self._request(
            "GET",
            "/images",
            image_list_adapter,
            common_error_adapter,
        )

    # Firewall rulesets

    async def list_firewall_rulesets(self) -> list[FirewallRuleset]:
        """List firewall rulesets.

        Returns:
            List of firewall rulesets
        """
        return await self._request(
            "GET",
            "/firewall-rulesets",
            firewall_ruleset_list_adapter,
            firewall_ruleset_error_adapter,
        )
