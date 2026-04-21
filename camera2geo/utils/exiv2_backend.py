import os
import shutil
from fractions import Fraction
from importlib import import_module
from pathlib import Path

from .metadata import ImageMetadata


def _get_exiv2():
    try:
        return import_module("exiv2")
    except ImportError as exc:
        raise ImportError(
            "camera2geo requires the 'exiv2' Python package for metadata operations."
        ) from exc


def _open_image(image_path: str):
    exiv2 = _get_exiv2()
    image = exiv2.ImageFactory.open(str(image_path))
    image.readMetadata()
    return image


def _datum_to_string(container, key: str):
    if key not in container:
        return None
    return container[key].toString()


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


def _gps_to_decimal(exif_data, coord_key: str, ref_key: str):
    if coord_key not in exif_data:
        return None

    coord_value = exif_data[coord_key].value()
    parts = list(coord_value)
    if len(parts) != 3:
        return _parse_number(exif_data[coord_key].toString())

    degrees = _parse_fraction(parts[0])
    minutes = _parse_fraction(parts[1])
    seconds = _parse_fraction(parts[2])
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

    ref = _datum_to_string(exif_data, ref_key)
    if ref and ref.upper() in {"S", "W"}:
        decimal *= -1
    return decimal


def _decimal_to_dms(decimal_value: float):
    absolute_value = abs(float(decimal_value))
    degrees = int(absolute_value)
    minutes_full = (absolute_value - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return [
        (degrees, 1),
        (minutes, 1),
        (round(seconds * 1000000), 1000000),
    ]


def read_image_metadata(image_path: str) -> dict:
    image = _open_image(image_path)
    exif_data = image.exifData()
    xmp_data = image.xmpData()

    raw_metadata = {
        "File.FileName": os.path.basename(image_path),
        "Exif.GPSInfo.GPSLatitude": _gps_to_decimal(
            exif_data, "Exif.GPSInfo.GPSLatitude", "Exif.GPSInfo.GPSLatitudeRef"
        ),
        "Exif.GPSInfo.GPSLongitude": _gps_to_decimal(
            exif_data, "Exif.GPSInfo.GPSLongitude", "Exif.GPSInfo.GPSLongitudeRef"
        ),
        "Exif.GPSInfo.GPSAltitude": _parse_number(
            _datum_to_string(exif_data, "Exif.GPSInfo.GPSAltitude")
        ),
        "Exif.Photo.FocalLength": _parse_number(
            _datum_to_string(exif_data, "Exif.Photo.FocalLength")
        ),
        "Exif.Photo.FocalLengthIn35mmFilm": _parse_number(
            _datum_to_string(exif_data, "Exif.Photo.FocalLengthIn35mmFilm")
        ),
        "Exif.Photo.PixelXDimension": _parse_number(
            _datum_to_string(exif_data, "Exif.Photo.PixelXDimension")
            or _datum_to_string(exif_data, "Exif.Image.ImageWidth")
        ),
        "Exif.Photo.PixelYDimension": _parse_number(
            _datum_to_string(exif_data, "Exif.Photo.PixelYDimension")
            or _datum_to_string(exif_data, "Exif.Image.ImageLength")
        ),
        "Exif.Photo.MaxApertureValue": _parse_number(
            _datum_to_string(exif_data, "Exif.Photo.MaxApertureValue")
        ),
        "Exif.Photo.DateTimeOriginal": _parse_datetime(
            _datum_to_string(exif_data, "Exif.Photo.DateTimeOriginal")
        ),
        "Exif.Image.Model": _datum_to_string(exif_data, "Exif.Image.Model"),
        "Exif.Image.Make": _datum_to_string(exif_data, "Exif.Image.Make"),
        "Xmp.drone-dji.RelativeAltitude": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.RelativeAltitude")
        ),
        "Xmp.drone-dji.AbsoluteAltitude": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.AbsoluteAltitude")
        ),
        "Xmp.drone-dji.GimbalRollDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.GimbalRollDegree")
        ),
        "Xmp.drone-dji.GimbalPitchDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.GimbalPitchDegree")
        ),
        "Xmp.drone-dji.GimbalYawDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.GimbalYawDegree")
        ),
        "Xmp.drone-dji.Roll": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.Roll")
        ),
        "Xmp.drone-dji.Pitch": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.Pitch")
        ),
        "Xmp.drone-dji.Yaw": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.Yaw")
        ),
        "Xmp.drone-dji.FlightPitchDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.FlightPitchDegree")
        ),
        "Xmp.drone-dji.FlightRollDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.FlightRollDegree")
        ),
        "Xmp.drone-dji.FlightYawDegree": _parse_number(
            _datum_to_string(xmp_data, "Xmp.drone-dji.FlightYawDegree")
        ),
        "Xmp.drone-dji.RigCameraIndex": _datum_to_string(
            xmp_data, "Xmp.drone-dji.RigCameraIndex"
        ),
        "Xmp.drone-dji.SensorIndex": _datum_to_string(
            xmp_data, "Xmp.drone-dji.SensorIndex"
        ),
    }
    return ImageMetadata(
        file_name=raw_metadata["File.FileName"],
        latitude=float(raw_metadata["Exif.GPSInfo.GPSLatitude"]),
        longitude=float(raw_metadata["Exif.GPSInfo.GPSLongitude"]),
        gps_altitude=raw_metadata["Exif.GPSInfo.GPSAltitude"],
        focal_length=float(raw_metadata["Exif.Photo.FocalLength"]),
        focal_length35mm=raw_metadata["Exif.Photo.FocalLengthIn35mmFilm"],
        relative_altitude=raw_metadata["Xmp.drone-dji.RelativeAltitude"],
        absolute_altitude=raw_metadata["Xmp.drone-dji.AbsoluteAltitude"],
        gimbal_roll_degree=raw_metadata["Xmp.drone-dji.GimbalRollDegree"]
        if raw_metadata["Xmp.drone-dji.GimbalRollDegree"] is not None
        else (raw_metadata["Xmp.drone-dji.Roll"] or 0.0),
        gimbal_pitch_degree=raw_metadata["Xmp.drone-dji.GimbalPitchDegree"]
        if raw_metadata["Xmp.drone-dji.GimbalPitchDegree"] is not None
        else (raw_metadata["Xmp.drone-dji.Pitch"] or 0.0),
        gimbal_yaw_degree=raw_metadata["Xmp.drone-dji.GimbalYawDegree"]
        if raw_metadata["Xmp.drone-dji.GimbalYawDegree"] is not None
        else (raw_metadata["Xmp.drone-dji.Yaw"] or 0.0),
        flight_pitch_degree=raw_metadata["Xmp.drone-dji.FlightPitchDegree"]
        if raw_metadata["Xmp.drone-dji.FlightPitchDegree"] is not None
        else 999.0,
        flight_roll_degree=raw_metadata["Xmp.drone-dji.FlightRollDegree"]
        if raw_metadata["Xmp.drone-dji.FlightRollDegree"] is not None
        else 999.0,
        flight_yaw_degree=raw_metadata["Xmp.drone-dji.FlightYawDegree"]
        if raw_metadata["Xmp.drone-dji.FlightYawDegree"] is not None
        else 999.0,
        image_width=int(raw_metadata["Exif.Photo.PixelXDimension"]),
        image_height=int(raw_metadata["Exif.Photo.PixelYDimension"]),
        max_aperture_value=raw_metadata["Exif.Photo.MaxApertureValue"],
        datetime_original=raw_metadata["Exif.Photo.DateTimeOriginal"],
        sensor_model_data=raw_metadata["Exif.Image.Model"],
        sensor_index=str(
            raw_metadata["Xmp.drone-dji.RigCameraIndex"]
            or raw_metadata["Xmp.drone-dji.SensorIndex"]
            or ""
        ),
        sensor_make=raw_metadata["Exif.Image.Make"],
        raw_metadata=raw_metadata,
    )


def read_metadata_batch(image_paths: list[str]) -> list[dict]:
    return [read_image_metadata(path) for path in image_paths]


def _delete_exif_gps_field(exif_data, coord_key: str, ref_key: str):
    for key in (coord_key, ref_key):
        if key in exif_data:
            del exif_data[key]


def _set_metadata_value(image, tag: str, value):
    if tag == "Exif.GPSInfo.GPSLatitude":
        exif_data = image.exifData()
        if value is None:
            _delete_exif_gps_field(
                exif_data, "Exif.GPSInfo.GPSLatitude", "Exif.GPSInfo.GPSLatitudeRef"
            )
            return
        exif_data["Exif.GPSInfo.GPSLatitude"] = _decimal_to_dms(float(value))
        exif_data["Exif.GPSInfo.GPSLatitudeRef"] = "N" if float(value) >= 0 else "S"
        return

    if tag == "Exif.GPSInfo.GPSLongitude":
        exif_data = image.exifData()
        if value is None:
            _delete_exif_gps_field(
                exif_data,
                "Exif.GPSInfo.GPSLongitude",
                "Exif.GPSInfo.GPSLongitudeRef",
            )
            return
        exif_data["Exif.GPSInfo.GPSLongitude"] = _decimal_to_dms(float(value))
        exif_data["Exif.GPSInfo.GPSLongitudeRef"] = "E" if float(value) >= 0 else "W"
        return

    if tag.startswith("Exif."):
        container = image.exifData()
    elif tag.startswith("Xmp."):
        container = image.xmpData()
    elif tag.startswith("Iptc."):
        container = image.iptcData()
    else:
        raise ValueError(f"Unsupported metadata tag: {tag}")

    if value is None:
        if tag in container:
            del container[tag]
        return

    if tag == "Exif.GPSInfo.GPSAltitude" and isinstance(value, (int, float)):
        container[tag] = str(Fraction(float(value)).limit_denominator())
        return

    container[tag] = str(value) if isinstance(value, (int, float)) else value


def apply_metadata_updates(
    input_image_paths: list[str],
    output_image_paths: list[str],
    *,
    metadata: dict[str, object],
    csv_rows: dict[str, dict] | None = None,
    csv_field_to_header: dict[str, str] | None = None,
):
    matched_rows = 0

    for in_path, out_path in zip(input_image_paths, output_image_paths):
        if str(in_path) != str(out_path):
            shutil.copy2(str(in_path), str(out_path))

        image = _open_image(str(out_path))
        for tag, value in metadata.items():
            _set_metadata_value(image, tag, value)

        if csv_rows and csv_field_to_header:
            base_name = Path(in_path).name.lower()
            stem_name = Path(in_path).stem.lower()
            row = csv_rows.get(base_name) or csv_rows.get(stem_name)
            if row is not None:
                matched_rows += 1
                for tag, csv_col in csv_field_to_header.items():
                    if tag == "name":
                        continue
                    if csv_col in row and row[csv_col] not in ("", None):
                        _set_metadata_value(image, tag, row[csv_col])

        image.writeMetadata()

    return matched_rows
