import os
import re
from fractions import Fraction
from importlib import import_module

from .metadata import ImageMetadata


XMP_KEYS = (
    "RelativeAltitude",
    "AbsoluteAltitude",
    "GimbalRollDegree",
    "GimbalPitchDegree",
    "GimbalYawDegree",
    "Roll",
    "Pitch",
    "Yaw",
    "FlightPitchDegree",
    "FlightRollDegree",
    "FlightYawDegree",
    "RigCameraIndex",
    "SensorIndex",
)


def _get_exifread():
    try:
        return import_module("exifread")
    except ImportError as exc:
        raise ImportError(
            "camera2geo requires the 'ExifRead' Python package for metadata reads."
        ) from exc


def _parse_fraction(value) -> float:
    if isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        return float(numerator) / float(denominator)
    return float(Fraction(str(value)))


def _parse_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value

    value_str = str(value).strip()
    if "/" in value_str:
        return _parse_fraction(value_str)
    return float(value_str)


def _parse_datetime(value):
    if value is None:
        return None
    return str(value).replace("-", ":", 2).replace("T", " ").split(".")[0]


def _extract_exif_value(tags, key: str):
    tag = tags.get(key)
    if tag is None:
        return None
    if hasattr(tag, "values"):
        values = tag.values
        if isinstance(values, list):
            return values
    return str(tag)


def _parse_exif_single(tags, *keys):
    for key in keys:
        value = _extract_exif_value(tags, key)
        if value not in (None, "", []):
            if isinstance(value, list) and len(value) == 1:
                return value[0]
            return value
    return None


def _ratio_to_float(value):
    if hasattr(value, "num") and hasattr(value, "den"):
        return float(value.num) / float(value.den)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return float(value.numerator) / float(value.denominator)
    return _parse_number(value)


def _gps_to_decimal(tags, coord_key: str, ref_key: str):
    coords = _extract_exif_value(tags, coord_key)
    if not coords:
        return None

    if not isinstance(coords, list):
        return _parse_number(coords)

    if len(coords) != 3:
        return _parse_number(coords[0]) if coords else None

    decimal = (
        _ratio_to_float(coords[0])
        + (_ratio_to_float(coords[1]) / 60.0)
        + (_ratio_to_float(coords[2]) / 3600.0)
    )

    ref = _parse_exif_single(tags, ref_key)
    if ref and str(ref).upper() in {"S", "W"}:
        decimal *= -1
    return decimal


def _read_xmp_fields(image_path: str) -> dict[str, str | None]:
    with open(image_path, "rb") as handle:
        text = handle.read().decode("utf-8", errors="ignore")

    values = {}
    for key in XMP_KEYS:
        attr_match = re.search(rf'(?:drone-dji|drone):{key}="([^"]+)"', text)
        if attr_match:
            values[f"Xmp.drone-dji.{key}"] = attr_match.group(1)
            continue

        elem_match = re.search(
            rf"<(?:drone-dji|drone):{key}>(.*?)</(?:drone-dji|drone):{key}>",
            text,
            flags=re.DOTALL,
        )
        values[f"Xmp.drone-dji.{key}"] = (
            elem_match.group(1).strip() if elem_match else None
        )

    return values


def _read_raw_metadata(image_path: str) -> dict:
    exifread = _get_exifread()
    with open(image_path, "rb") as handle:
        tags = exifread.process_file(handle, details=False)

    xmp = _read_xmp_fields(image_path)
    return {
        "File FileName": os.path.basename(image_path),
        "GPS GPSLatitude": _gps_to_decimal(
            tags, "GPS GPSLatitude", "GPS GPSLatitudeRef"
        ),
        "GPS GPSLongitude": _gps_to_decimal(
            tags, "GPS GPSLongitude", "GPS GPSLongitudeRef"
        ),
        "GPS GPSAltitude": _parse_number(
            _parse_exif_single(tags, "GPS GPSAltitude")
        ),
        "EXIF FocalLength": _parse_number(
            _parse_exif_single(tags, "EXIF FocalLength")
        ),
        "EXIF FocalLengthIn35mmFilm": _parse_number(
            _parse_exif_single(tags, "EXIF FocalLengthIn35mmFilm")
        ),
        "EXIF ExifImageWidth": _parse_number(
            _parse_exif_single(tags, "EXIF ExifImageWidth")
        ),
        "Image ImageWidth": _parse_number(
            _parse_exif_single(tags, "Image ImageWidth")
        ),
        "EXIF ExifImageLength": _parse_number(
            _parse_exif_single(tags, "EXIF ExifImageLength")
        ),
        "Image ImageLength": _parse_number(
            _parse_exif_single(tags, "Image ImageLength")
        ),
        "EXIF MaxApertureValue": _parse_number(
            _parse_exif_single(tags, "EXIF MaxApertureValue")
        ),
        "EXIF DateTimeOriginal": _parse_datetime(
            _parse_exif_single(tags, "EXIF DateTimeOriginal")
        ),
        "Image Model": _parse_exif_single(tags, "Image Model"),
        "Image Make": _parse_exif_single(tags, "Image Make"),
        "XMP drone-dji RelativeAltitude": _parse_number(
            xmp["Xmp.drone-dji.RelativeAltitude"]
        ),
        "XMP drone-dji AbsoluteAltitude": _parse_number(
            xmp["Xmp.drone-dji.AbsoluteAltitude"]
        ),
        "XMP drone-dji GimbalRollDegree": _parse_number(
            xmp["Xmp.drone-dji.GimbalRollDegree"]
        ),
        "XMP drone-dji GimbalPitchDegree": _parse_number(
            xmp["Xmp.drone-dji.GimbalPitchDegree"]
        ),
        "XMP drone-dji GimbalYawDegree": _parse_number(
            xmp["Xmp.drone-dji.GimbalYawDegree"]
        ),
        "XMP drone-dji Roll": _parse_number(xmp["Xmp.drone-dji.Roll"]),
        "XMP drone-dji Pitch": _parse_number(xmp["Xmp.drone-dji.Pitch"]),
        "XMP drone-dji Yaw": _parse_number(xmp["Xmp.drone-dji.Yaw"]),
        "XMP drone-dji FlightPitchDegree": _parse_number(
            xmp["Xmp.drone-dji.FlightPitchDegree"]
        ),
        "XMP drone-dji FlightRollDegree": _parse_number(
            xmp["Xmp.drone-dji.FlightRollDegree"]
        ),
        "XMP drone-dji FlightYawDegree": _parse_number(
            xmp["Xmp.drone-dji.FlightYawDegree"]
        ),
        "XMP drone-dji RigCameraIndex": xmp["Xmp.drone-dji.RigCameraIndex"],
        "XMP drone-dji SensorIndex": xmp["Xmp.drone-dji.SensorIndex"],
    }


def read_image_metadata(image_path: str) -> ImageMetadata:
    return ImageMetadata(tags=_read_raw_metadata(image_path))


def read_metadata_batch(image_paths: list[str]) -> list[ImageMetadata]:
    return [read_image_metadata(path) for path in image_paths]
