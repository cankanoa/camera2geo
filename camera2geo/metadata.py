import exiftool
import yaml
import shutil
import os

from typing import Dict, Any, List

from .utils.io import _resolve_paths


def read_metadata(input_images: str | List[str]):
    """
    Read metadata from one or more images and print the results as YAML and return values. Each parameter includes all metadata source fields that contribute to its value (primary + fallback).

    Args:
        input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.JPG", "/input/folder" (assumes *.JPG), ["/input/one.JPG", "/input/two.JPG"].

    Returns:
        dict: Mapping of image paths to grouped metadata key/value dictionaries.
    """

    print(f"Run read_metadata on {input_images}")

    input_image_paths = _resolve_paths(
        "search", input_images, kwargs={"default_file_pattern": "*.JPG"}
    )

    results = {}

    with exiftool.ExifToolHelper() as et:

        for image_path in input_image_paths:
            md = et.get_metadata(image_path)[0]

            def get_many(keys: List[str]):
                return {k: md.get(k) for k in keys}

            data = {
                "file_name": get_many(["File:FileName"]),
                "latitude": get_many(["Composite:GPSLatitude", "EXIF:GPSLatitude"]),
                "longitude": get_many(["Composite:GPSLongitude", "EXIF:GPSLongitude"]),
                "focal_length": get_many(["EXIF:FocalLength"]),
                "focal_length35mm": get_many(["EXIF:FocalLengthIn35mmFormat"]),
                "relative_altitude": get_many(
                    ["XMP:RelativeAltitude", "Composite:GPSAltitude"]
                ),
                "absolute_altitude": get_many(
                    ["XMP:AbsoluteAltitude", "Composite:GPSAltitude"]
                ),
                "gimbal_roll_degree": get_many(
                    [
                        "XMP:GimbalRollDegree",
                        "MakerNotes:CameraRoll",
                        "XMP:Roll",
                    ]
                ),
                "gimbal_pitch_degree": get_many(
                    [
                        "XMP:GimbalPitchDegree",
                        "MakerNotes:CameraPitch",
                        "XMP:Pitch",
                    ]
                ),
                "gimbal_yaw_degree": get_many(
                    [
                        "XMP:GimbalYawDegree",
                        "MakerNotes:CameraYaw",
                        "XMP:Yaw",
                    ]
                ),
                "flight_pitch_degree": get_many(
                    ["XMP:FlightPitchDegree", "MakerNotes:Pitch"]
                ),
                "flight_roll_degree": get_many(
                    ["XMP:FlightRollDegree", "MakerNotes:Roll"]
                ),
                "flight_yaw_degree": get_many(
                    ["XMP:FlightYawDegree", "MakerNotes:Yaw"]
                ),
                "image_width": get_many(["EXIF:ImageWidth", "EXIF:ExifImageWidth"]),
                "image_height": get_many(["EXIF:ImageHeight", "EXIF:ExifImageHeight"]),
                "max_aperture_value": get_many(["EXIF:MaxApertureValue"]),
                "datetime_original": get_many(["EXIF:DateTimeOriginal"]),
                "sensor_model_data": get_many(["EXIF:Model"]),
                "sensor_index": get_many(["XMP:RigCameraIndex", "XMP:SensorIndex"]),
                "sensor_make": get_many(["EXIF:Make"]),
            }

            results[str(image_path)] = data

    print(yaml.dump(results, sort_keys=False))
    return results


def apply_metadata(
    input_images: str | List[str],
    metadata: Dict[str, Any] | None = None,
    output_images: str | List[str] | None = None,
    csv_metadata_path: str | None = None,
    csv_field_to_header: Dict[str, str] | None = None,
):
    """
    Apply or remove metadata on one or more images. If `output_images` is not provided, edits are applied in-place; otherwise, input files are copied first.

    Args:
        input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.JPG", "/input/folder" (assumes *.JPG), ["/input/one.JPG", "/input/two.JPG"].
        metadata (Dict[str, Any]): Dictionary of metadata updates. Keys are tag names (e.g., "EXIF:FocalLength") and values are tag values (e.g. 10.4 to set to float or None to remove metadata field from image). e.g. {"EXIF:FocalLength": 10.4}.
        output_images (str | List[str], optional): If not provided, input image metadata will be updated. If provided: defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Meta.tif), ["/input/one.tif", "/input/two.tif"].
        csv_metadata_path (str | None): Optional CSV file containing per-image metadata rows. Must include a column with the basename (without the extension) of the image file (e.g., "image_0123").
        csv_field_to_header (Dict[str, str] | None): Mapping from metadata tag name to CSV column name. Required if `csv_metadata_path` is provided. Must include a "name":"<column_to_basename_of_image_to_match>" mapping. The same exif tag cannot be used in both `metadata` and `csv_metadata_path`. e.g. {"EXIF:FocalLength": "focal_length"}.

    Returns:
        list[str]: Paths of the modified images.
    """
    print(f"Run apply_metadata on {input_images}")

    # Validate metadata overlap
    metadata = metadata or {}
    if csv_metadata_path and csv_field_to_header:
        overlap = set(metadata.keys()) & set(csv_field_to_header.keys())
        if overlap:
            raise ValueError(
                f"Tags cannot appear in both metadata and csv_field_to_header: {sorted(overlap)}"
            )

    # Validate CSV requirement
    if csv_metadata_path and not csv_field_to_header:
        raise ValueError("csv_field_to_header is required when csv_metadata_path is provided.")

    if csv_field_to_header and "name" not in csv_field_to_header:
        raise ValueError(
            'csv_field_to_header must include a "name": "<csv_column_for_image_basename>" entry.'
        )

    # Resolve paths
    input_image_paths = _resolve_paths(
        "search", input_images, kwargs={"default_file_pattern": "*.JPG"}
    )

    if output_images is None:
        output_image_paths = input_image_paths
    else:
        output_image_paths = _resolve_paths(
            "create",
            output_images,
            kwargs={
                "paths_or_bases": input_image_paths,
                "default_file_pattern": "$_Meta.tif",
            },
        )

    # Split global metadata
    tags_to_set = {k: v for k, v in metadata.items() if v is not None}
    tags_to_delete = [k for k, v in metadata.items() if v is None]

    # Load CSV metadata
    csv_rows = None
    if csv_metadata_path:
        import csv

        csv_rows = {}
        with open(csv_metadata_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            name_col = csv_field_to_header["name"]
            if name_col not in reader.fieldnames:
                raise ValueError(
                    f'CSV missing required name column "{name_col}" defined in csv_field_to_header["name"].'
                )

            for row in reader:
                key = row[name_col]
                if key:
                    csv_rows[key.lower()] = row

    # Apply metadata
    matched_rows = 0
    with exiftool.ExifToolHelper() as et:
        for in_path, out_path in zip(input_image_paths, output_image_paths):

            if str(in_path) != str(out_path):
                shutil.copy2(str(in_path), str(out_path))

            # Apply global metadata
            if tags_to_set:
                et.set_tags(
                    [str(out_path)],
                    tags_to_set,
                    params=["-overwrite_original_in_place"],
                )
            for tag in tags_to_delete:
                et.execute("-overwrite_original_in_place", f"-{tag}=", str(out_path))

            # Apply CSV metadata (per image)
            if csv_rows:
                base = os.path.basename(in_path).lower()
                if base in csv_rows:
                    matched_rows += 1
                    row = csv_rows[base]

                    csv_updates = {}
                    for tag, csv_col in csv_field_to_header.items():
                        if tag == "name":
                            continue
                        if csv_col in row and row[csv_col] not in ("", None):
                            csv_updates[tag] = row[csv_col]

                    if csv_updates:
                        et.set_tags(
                            [str(out_path)],
                            csv_updates,
                            params=["-overwrite_original_in_place"],
                        )
        print(f"Matched {matched_rows} images with CSV metadata")
    return output_image_paths