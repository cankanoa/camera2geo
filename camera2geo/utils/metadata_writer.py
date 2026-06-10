import shutil
from fractions import Fraction
from importlib import import_module
from pathlib import Path


def _get_exiv2():
    try:
        return import_module("exiv2")
    except ImportError as exc:
        raise ImportError(
            "camera2geo requires the 'exiv2' Python package for metadata write operations."
        ) from exc


def _open_image(image_path: str):
    exiv2 = _get_exiv2()
    image = exiv2.ImageFactory.open(str(image_path))
    image.readMetadata()
    return image


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
