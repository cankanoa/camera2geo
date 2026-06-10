import os

from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle


OPENTOPO_CACHE_DIRNAME = "_elevation_cache"
OPENTOPO_CACHE_FILENAME = "opentopo_surface.tif"
WGS84_CRS = QgsCoordinateReferenceSystem.fromEpsgId(4326)


def get_opentopo_cache_file(plugin_dir: str) -> str:
    return os.path.join(
        plugin_dir, OPENTOPO_CACHE_DIRNAME, OPENTOPO_CACHE_FILENAME
    )


def serialize_extent(rect: QgsRectangle) -> str:
    return (
        "["
        f"{rect.xMinimum()}, {rect.yMinimum()}, "
        f"{rect.xMaximum()}, {rect.yMaximum()}"
        "]"
    )


def deserialize_extent(text: str) -> QgsRectangle | None:
    cleaned = (text or "").strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    parts = [part.strip() for part in cleaned.split(",")]
    if len(parts) != 4:
        return None
    west, south, east, north = (float(part) for part in parts)
    return QgsRectangle(west, south, east, north)
