# Functions
from .main import camera2geo
from .search import search_cameras, search_lenses
__all__ = [
    "camera2geo",
    "search_cameras",
    "search_lenses",
    ]

# Name
name = "camera2geo"

# Import version from pyproject.toml
from importlib.metadata import version, PackageNotFoundError
try:
    __version__ = version("camera2geo")
except PackageNotFoundError:
    __version__ = "0.0.0"
