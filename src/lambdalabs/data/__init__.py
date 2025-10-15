"""Lambda Labs Cloud API data files."""

from importlib.resources import files


def get_openapi_spec() -> str:
    """Load the Lambda Cloud API OpenAPI specification.

    Returns:
        OpenAPI spec as JSON string

    Example:
        >>> import json
        >>> from lambdalabs.data import get_openapi_spec
        >>> spec = json.loads(get_openapi_spec())
        >>> spec["info"]["version"]
        '1.8.3'
    """
    return files(__package__).joinpath("openapi-spec.json").read_text()


__all__ = ["get_openapi_spec"]
