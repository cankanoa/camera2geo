from importlib.metadata import version, PackageNotFoundError

name = "camera2geo"

# Import version from pyproject.toml
try:
    __version__ = version("camera2geo")
except PackageNotFoundError:
    __version__ = "0.0.0"
