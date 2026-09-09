"""Blender integration through the Model Context Protocol."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("blender-mcp")
except PackageNotFoundError:
    # Package is not installed (e.g. running from a source checkout)
    __version__ = "unknown"

from .connection import BlenderConnection


def get_blender_connection():
    """Load legacy integrations only when a legacy caller requests them."""
    from .server import get_blender_connection as legacy_connection
    return legacy_connection()
