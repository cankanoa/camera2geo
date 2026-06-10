from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


OPENTOPO_GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"
OPENTOPO_DEMTYPE = "SRTMGL1_E"


def parse_extent_4326(extent: str | tuple[float, float, float, float] | list[float]):
    if isinstance(extent, str):
        cleaned = extent.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]
        parts = [part.strip() for part in cleaned.split(",")]
        if len(parts) != 4:
            raise ValueError(
                "OpenTopo extent must contain west,south,east,north in EPSG:4326."
            )
        west, south, east, north = (float(part) for part in parts)
    elif isinstance(extent, (tuple, list)) and len(extent) == 4:
        west, south, east, north = (float(value) for value in extent)
    else:
        raise ValueError(
            "OpenTopo extent must be a 4-value tuple/list or 'west,south,east,north' string."
        )

    if not west < east or not south < north:
        raise ValueError(
            "OpenTopo extent must satisfy west < east and south < north."
        )

    return west, south, east, north


def download_opentopo_dem(
    *,
    extent_4326: str | tuple[float, float, float, float] | list[float],
    api_key: str,
    output_path: str,
    demtype: str = OPENTOPO_DEMTYPE,
    progress_callback=None,
) -> str:
    if not api_key or not api_key.strip():
        raise ValueError(
            "An OpenTopography API key is required for elevation_surface='opentopo_extent'."
        )

    west, south, east, north = parse_extent_4326(extent_4326)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _remove_existing_cached_raster(output)

    query = urlencode(
        {
            "demtype": demtype,
            "south": south,
            "north": north,
            "west": west,
            "east": east,
            "outputFormat": "GTiff",
            "API_Key": api_key.strip(),
        }
    )
    url = f"{OPENTOPO_GLOBALDEM_URL}?{query}"

    try:
        with urlopen(url) as response, open(output, "wb") as destination:
            total_size = response.headers.get("Content-Length")
            total_size = int(total_size) if total_size else 0
            downloaded = 0
            chunk_size = 1024 * 128
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                destination.write(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    if total_size > 0:
                        progress_callback(downloaded / total_size)
                    else:
                        progress_callback(None)
    except HTTPError as err:
        raise RuntimeError(_format_opentopo_http_error(err)) from err
    except URLError as err:
        raise RuntimeError(f"Unable to reach OpenTopography: {err}") from err

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("OpenTopography returned an empty elevation raster.")

    return str(output)


def _remove_existing_cached_raster(output: Path):
    for suffix in ("", ".aux.xml", ".ovr"):
        candidate = Path(f"{output}{suffix}")
        if candidate.exists():
            candidate.unlink()


def _format_opentopo_http_error(err: HTTPError) -> str:
    response_text = ""
    try:
        response_text = err.read().decode("utf-8", errors="replace").strip()
    except Exception:
        response_text = ""

    if err.code == 204:
        return "OpenTopography returned no data for the requested extent."
    if err.code == 401:
        return "OpenTopography rejected the API key."
    if response_text:
        return (
            f"OpenTopography request failed with HTTP {err.code}: "
            f"{err.reason}. Response: {response_text}"
        )
    return f"OpenTopography request failed with HTTP {err.code}: {err.reason}"
