import exiftool
import yaml
import shutil

from typing import Dict, Any, List

from .utils.io import _resolve_paths


def read_metadata(
    input_images: str | List[str]
    ):
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

                "relative_altitude": get_many(["XMP:RelativeAltitude", "Composite:GPSAltitude"]),
                "absolute_altitude": get_many(["XMP:AbsoluteAltitude", "Composite:GPSAltitude"]),

                "gimbal_roll_degree": get_many([
                    "XMP:GimbalRollDegree",
                    "MakerNotes:CameraRoll",
                    "XMP:Roll",
                ]),
                "gimbal_pitch_degree": get_many([
                    "XMP:GimbalPitchDegree",
                    "MakerNotes:CameraPitch",
                    "XMP:Pitch",
                ]),
                "gimbal_yaw_degree": get_many([
                    "XMP:GimbalYawDegree",
                    "MakerNotes:CameraYaw",
                    "XMP:Yaw",
                ]),

                "flight_pitch_degree": get_many([
                    "XMP:FlightPitchDegree",
                    "MakerNotes:Pitch"
                ]),
                "flight_roll_degree": get_many([
                    "XMP:FlightRollDegree",
                    "MakerNotes:Roll"
                ]),
                "flight_yaw_degree": get_many([
                    "XMP:FlightYawDegree",
                    "MakerNotes:Yaw"
                ]),

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
        metadata: Dict[str, Any],
        output_images: str | List[str] | None = None,
    ):
    """
    Apply or remove metadata on one or more images. If `output_images` is not provided, edits are applied in-place; otherwise, input files are copied first.

    Args:
        input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.JPG", "/input/folder" (assumes *.JPG), ["/input/one.JPG", "/input/two.JPG"].
        metadata (Dict[str, Any]): Dictionary of metadata updates. Keys are tag names (e.g., "EXIF:FocalLength") and values are tag values (e.g. 10.4 to set to float or None to remove metadata field from image).
        output_images (str | List[str], required): Defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Meta.tif), ["/input/one.tif", "/input/two.tif"].

    Returns:
        list[str]: Paths of the modified images.
    """
    print(f"Run apply_metadata on {input_images}")

    input_image_paths = _resolve_paths(
        "search", input_images, kwargs={"default_file_pattern": "*.JPG"}
    )

    # If no output_images → modify in-place
    if output_images is None:
        output_image_paths = input_image_paths
    else:
        output_image_paths = _resolve_paths(
            "create",
            output_images,
            kwargs={"paths_or_bases": input_image_paths, "default_file_pattern": "$_Meta.tif"},
        )

    # Split into set and delete operations
    tags_to_set = {k: v for k, v in metadata.items() if v is not None}
    tags_to_delete = [k for k, v in metadata.items() if v is None]

    print("Will SET:", tags_to_set)
    print("Will REMOVE:", tags_to_delete)

    with exiftool.ExifToolHelper() as et:
        for in_path, out_path in zip(input_image_paths, output_image_paths):

            # If output path is different → copy the image file
            if str(in_path) != str(out_path):
                shutil.copy2(str(in_path), str(out_path))

            # SET TAGS (normal)
            if tags_to_set:
                et.set_tags(
                    [str(out_path)],
                    tags_to_set,
                    params=["-overwrite_original_in_place"]
                )

            # DELETE TAGS (must use execute)
            for tag in tags_to_delete:
                et.execute(
                    "-overwrite_original_in_place",
                    f"-{tag}=",
                    str(out_path)
                )

    return output_image_paths