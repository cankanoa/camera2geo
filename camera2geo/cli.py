import fire
import camera2geo
import inspect
from importlib.metadata import version as get_version, PackageNotFoundError
import sys


def _cli_version():
    try:
        print(get_version("camera2geo"))
    except PackageNotFoundError:
        print("camera2geo (version unknown)")


def _build_cli():
    class CLI:
        pass

    for name in camera2geo.__all__:
        func = getattr(camera2geo, name, None)
        if callable(func):
            func.__doc__ = inspect.getdoc(func) or "No description available."
            setattr(CLI, name, staticmethod(func))

    return CLI


def main():
    sys.stdout.reconfigure(line_buffering=True)

    if "--version" in sys.argv:
        _cli_version()
        return

    fire.Fire(_build_cli())