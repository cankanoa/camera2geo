# Copyright (c) 2024
# Author: Dean Hand
# License: AGPL
# Version: 1.0

from pathlib import Path
from loguru import logger
from .utils import config
from .imagedrone import ImageDrone
from .new_fov import HighAccuracyFOVCalculator

def process_metadata(
    *,
    exif_record: dict,
    input_image_path: str,
    output_image_path: str,
    sensor_dimensions: dict,
    cog: bool,
    equalize: bool,
    lens_correction: bool,
    epsg: int,
    use_elevation_service: bool,
    dsm_path: str,
    correct_magnetic_declination: bool,
) -> str:
    """
    Process a single image's metadata and write exactly one output raster.

    Returns:
        str: The produced output_image_path.
    """
    # Update runtime flags (no file logging/geojson here)
    config.update_cog(cog)
    config.update_equalize(equalize)
    config.update_lense(lens_correction)
    config.update_epsg(epsg)
    config.update_elevation(use_elevation_service)
    config.update_dtm(dsm_path or "")
    config.update_correct_magnetic_declinaison(correct_magnetic_declination)

    # Ensure parent dir exists
    Path(output_image_path).parent.mkdir(parents=True, exist_ok=True)

    # Build the ImageDrone from EXIF + config
    image = ImageDrone(exif_record, sensor_dimensions, config)
    config.update_file_name(image.file_name)
    config.update_abso_altitude(image.absolute_altitude)
    config.update_rel_altitude(image.relative_altitude)

    # Compute FOV/footprint (if your geotiff generation uses it)
    image.coord_array, image.footprint_coordinates = HighAccuracyFOVCalculator(image).get_fov_bbox()

    # Generate the raster — write to the exact target path
    # NOTE: requires ImageDrone.generate_geotiff to accept an explicit output path
    # If your current method is generate_geotiff(in_dir, out_dir, logger),
    # see the note below to add an `output_path` param.
    image.generate_geotiff(
        input_dir=str(Path(input_image_path).parent),
        output_dir=str(Path(output_image_path).parent),
        logger=logger,
        output_path=str(output_image_path),  # <-- new/optional param (see note)
    )

    return str(output_image_path)