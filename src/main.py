import os
import datetime
from pathlib import Path
import warnings
import exiftool
import geojson

from typing import List

from .meta_data import process_metadata
from .utils.utils import read_sensor_dimensions_from_csv, _resolve_paths
from .utils.logger_config import logger, init_logger
from .utils.raster_utils import create_mosaic
from .utils import config

warnings.filterwarnings("ignore", category=FutureWarning, module="osgeo")

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
    use_nodejs_ui: bool = False,
    dsm_path: str | None = None,                 # replaces --DSMPATH (mutually exclusive with elevation service)
    use_elevation_service: bool = False,         # replaces --elevation_service
    sensor_info_csv: str = f"{os.path.dirname(os.path.abspath(__file__))}/drone_sensors.csv",
) -> list:
    """
    Process a folder of drone images into GeoTIFFs and a GeoJSON footprint file.

    Args:
    input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.tif", "/input/folder" (assumes *.tif), ["/input/one.tif", "/input/two.tif"].
    output_images (str | List[str], required): Defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Geo.tif), ["/input/one.tif", "/input/two.tif"].

    Returns:
        dict with keys:
          - feature_collection (dict)
          - geojson_path (Path)
          - geotiff_dir (Path)
          - mosaic_dir (Path | None)
          - num_images (int)
          - log_path (Path | None)
    """

    print(f"Run camera2geo on {input_images} to {output_images}")

    # Input and output paths
    input_image_paths = _resolve_paths(
        "search", input_images, kwargs={"default_file_pattern": "*.JPG"}
    )
    output_image_paths = _resolve_paths(
        "create",
        output_images,
        kwargs={
            "paths_or_bases": input_image_paths,
            "default_file_pattern": "$_Geo.tif",
        },
    )
    input_image_names = _resolve_paths("name", input_image_paths)

    now = datetime.datetime.now()

    # Config flags
    config.update_epsg(epsg)
    config.update_correct_magnetic_declinaison(correct_magnetic_declination)
    config.update_cog(cog)
    config.update_equalize(image_equalize)
    config.update_lense(lens_correction)
    config.update_elevation(use_elevation_service)
    config.update_nodejs_graphical_interface(use_nodejs_ui)

    # DSM / RTK detection
    if dsm_path:
        if not os.path.exists(dsm_path):
            raise ValueError(f"{dsm_path} is not a valid elevation file.", RuntimeWarning)
        else:
            config.update_dtm(dsm_path)
    else:
        config.update_dtm("")

    # Detect RTK sidecar(s)
    rtk_exts = {".obs", ".mrk", ".bin", ".nav"}
    rtk_present = any(
        os.path.splitext(p)[1].lower() in rtk_exts
        for p in input_image_paths
        for p in [Path(p).with_suffix(ext) for ext in rtk_exts]
        if Path(p).exists()
    )
    if rtk_present:
        config.update_rtk(True)

    # EXIF metadata
    with exiftool.ExifToolHelper() as et:
        exif_array: list[dict] = et.get_metadata(input_image_paths)
    if not exif_array:
        raise RuntimeError("Failed to extract metadata from image files.")

    # Sensor dimensions
    sensor_dimensions = read_sensor_dimensions_from_csv(
        sensor_info_csv, sensor_width_mm, sensor_height_mm
    )
    if sensor_dimensions is None:
        raise RuntimeError("Error reading sensor dimensions from CSV.")

    # Ensure output parents exist
    for p in output_image_paths:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    # Core processing
    produced_paths: list[str] = []
    for exif, in_path, out_path in zip(exif_array, input_image_paths, output_image_paths):
        produced = process_metadata(
            exif_record=exif,
            input_image_path=in_path,
            output_image_path=out_path,
            sensor_dimensions=sensor_dimensions,
            cog=cog,
            equalize=image_equalize,
            lens_correction=lens_correction,
            epsg=epsg,
            use_elevation_service=use_elevation_service,
            dsm_path=dsm_path or "",
            correct_magnetic_declination=correct_magnetic_declination,
        )
        produced_paths.append(produced if isinstance(produced, str) else out_path)

    return output_image_paths