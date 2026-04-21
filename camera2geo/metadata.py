import yaml

from dataclasses import asdict
from typing import Dict, Any, List

from .utils.io import _resolve_paths
from .utils.exiv2_backend import apply_metadata_updates, read_image_metadata


def read_metadata(input_images: str | List[str]):
    """
    Read metadata from one or more images and print the results as YAML and return values using native exiv2 tag names.

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

    for image_path in input_image_paths:
        md = read_image_metadata(str(image_path))
        results[str(image_path)] = asdict(md)

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
        metadata (Dict[str, Any]): Dictionary of metadata updates. Keys are exiv2 tag names (e.g., "Exif.Photo.FocalLength") and values are tag values (e.g. 10.4 to set to float or None to remove metadata field from image). e.g. {"Exif.Photo.FocalLength": 10.4}.
        output_images (str | List[str], optional): If not provided, input image metadata will be updated. If provided: defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Meta.tif), ["/input/one.tif", "/input/two.tif"].
        csv_metadata_path (str | None): Optional CSV file containing per-image metadata rows. Must include a column with the basename (without the extension) of the image file (e.g., "image_0123").
        csv_field_to_header (Dict[str, str] | None): Mapping from exiv2 tag name to CSV column name. Required if `csv_metadata_path` is provided. Must include a "name":"<column_to_basename_of_image_to_match>" mapping. The same tag cannot be used in both `metadata` and `csv_metadata_path`. e.g. {"Exif.Photo.FocalLength": "focal_length"}.

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

    matched_rows = apply_metadata_updates(
        [str(path) for path in input_image_paths],
        [str(path) for path in output_image_paths],
        metadata=metadata,
        csv_rows=csv_rows,
        csv_field_to_header=csv_field_to_header,
    )
    print(f"Matched {matched_rows} images with CSV metadata")
    return output_image_paths
