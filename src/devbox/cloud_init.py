"""Template handling with Jinja2 support."""

from __future__ import annotations

import base64
from importlib.resources import files
from typing import Any

from jinja2 import Template


def load_template(context: dict[str, Any], template_name: str) -> str:
    """Load and render template from package resources.

    The template is loaded from devbox/templates/ and rendered with the
    provided Jinja2 context variables.

    Args:
        context: Dictionary of variables for Jinja2 template rendering
        template_name: Name of the template file to load

    Returns:
        Rendered template content

    Raises:
        FileNotFoundError: If template file not found in package
        jinja2.TemplateError: If template rendering fails
    """
    # Load template from package resources
    template_path = files("devbox.templates").joinpath(template_name)
    template_text = template_path.read_text(encoding="utf-8")

    # Render with Jinja2
    template = Template(template_text)
    return template.render(**context)


def encode_cloud_init(content: str) -> str:
    """Encode cloud-init content to base64.

    Args:
        content: Cloud-init YAML content

    Returns:
        Base64-encoded string suitable for Lambda Cloud API user_data field
    """
    return base64.b64encode(content.encode("utf-8")).decode("ascii")
