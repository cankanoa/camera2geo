# Functions
from .main import camera2geo
from .search import search_cameras, search_lenses
from .metadata import apply_metadata, read_metadata

try:
    from .prep import add_relative_altitude_to_csv
except ImportError:
    add_relative_altitude_to_csv = None

__all__ = [
    "camera2geo",
    "search_cameras",
    "search_lenses",
    "apply_metadata",
    "read_metadata",
]

if add_relative_altitude_to_csv is not None:
    __all__.append("add_relative_altitude_to_csv")

# Name
name = "camera2geo"

# Import version from pyproject.toml
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("camera2geo")
except PackageNotFoundError:
    __version__ = "0.0.0"
