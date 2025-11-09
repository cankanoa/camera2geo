import os
import exiftool

from pathlib import Path
from typing import List

from .utils.utils import read_sensor_dimensions_from_csv, _resolve_paths
from .utils import config
from .utils.imagedrone import ImageDrone
from .utils.new_fov import HighAccuracyFOVCalculator

# Uses the following metadata: required: lat, long, agl, focal length, roll, yaw, pitch, width, height, datetime

def camera2geo(
    input_images: str | List[str],
    output_images: str | List[str],
    *,
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    epsg: int = 4326,
    correct_magnetic_declination: bool = False,
    cog: bool = False,
    image_equalize: bool = False,
    lens_correction: bool = False,
    elevation_data: str | bool = False,
    sensor_info_csv: str = f"{os.path.dirname(os.path.abspath(__file__))}/drone_sensors.csv",
) -> list:
    print(f"Run camera2geo on {input_images} to {output_images}")

    input_image_paths = _resolve_paths(
        "search", input_images, kwargs={"default_file_pattern": "*.JPG"}
    )
    output_image_paths = _resolve_paths(
        "create",
        output_images,
        kwargs={"paths_or_bases": input_image_paths, "default_file_pattern": "$_Geo.tif"},
    )

    # Set once
    config.update_epsg(epsg)
    config.update_correct_magnetic_declinaison(correct_magnetic_declination)
    config.update_cog(cog)
    config.update_equalize(image_equalize)
    config.update_lense(lens_correction)

    if elevation_data is False:
        config.update_elevation(False)  # No online
        config.update_dtm("")  # No local DSM

    elif elevation_data is True:
        config.update_elevation(True)  # Online elevation
        config.update_dtm("")  # No local DSM

    elif isinstance(elevation_data, str):
        config.update_elevation(False)  # Not online
        config.update_dtm(elevation_data)  # Use local DSM path

    with exiftool.ExifToolHelper() as et:
        exif_array = et.get_metadata(input_image_paths)

    sensor_dimensions = read_sensor_dimensions_from_csv(
        sensor_info_csv, sensor_width_mm, sensor_height_mm
    )

    for p in output_image_paths:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    produced_paths = []

    # Set per image
    for exif, in_path, out_path in zip(exif_array, input_image_paths, output_image_paths):

        # image–specific state (these must be set here)
        image = ImageDrone(exif, sensor_dimensions, config)
        config.update_file_name(image.file_name)
        config.update_abso_altitude(image.absolute_altitude)
        config.update_rel_altitude(image.relative_altitude)

        # footprint/FOV
        image.coord_array, image.footprint_coordinates = HighAccuracyFOVCalculator(image).get_fov_bbox()

        # generate geotiff to the explicit output path
        image.generate_geotiff(
            input_dir=str(Path(in_path).parent),
            output_dir=str(Path(out_path).parent),
            output_path=str(out_path),
        )

        produced_paths.append(str(out_path))

    return produced_paths