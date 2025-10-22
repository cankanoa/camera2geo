import os
import datetime
from pathlib import Path
import warnings
import exiftool
import geojson

from .meta_data import process_metadata
from .utils.utils import read_sensor_dimensions_from_csv
from .utils.logger_config import logger, init_logger
from .utils.raster_utils import create_mosaic
from .utils import config

warnings.filterwarnings("ignore", category=FutureWarning, module="osgeo")

def run_drone_footprints_pipeline(
    input_directory: str,
    output_directory: str,
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
    sensor_info_csv: str = f"{os.path.dirname(os.path.abspath(__file__))}/drone_sensors.csv",  # keep same default
    log_to_file: bool = True
) -> dict:
    """
    Process a folder of drone images into GeoTIFFs and a GeoJSON footprint file.

    Returns:
        dict with keys:
          - feature_collection (dict)
          - geojson_path (Path)
          - geotiff_dir (Path)
          - mosaic_dir (Path | None)
          - num_images (int)
          - log_path (Path | None)
    """
    now = datetime.datetime.now()

    # --- Validate inputs
    indir = Path(input_directory)
    outdir = Path(output_directory)
    if not indir.is_dir():
        raise NotADirectoryError(f"Input directory not found: {indir}")
    outdir.mkdir(parents=True, exist_ok=True)

    # --- Init logging
    log_path = None
    if log_to_file:
        log_file = f"L_M_{now.strftime('%Y-%m-%d_%H-%M')}.log"
        log_path = outdir / "logfiles" / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        init_logger(log_path=log_path)

    logger.info("Initializing processing of drone footprints")

    # --- Config flags (mirrors CLI switches)
    config.update_epsg(epsg)
    config.update_correct_magnetic_declinaison(correct_magnetic_declination)
    config.update_cog(cog)
    config.update_equalize(image_equalize)
    config.update_lense(lens_correction)
    config.update_elevation(use_elevation_service)
    config.update_nodejs_graphical_interface(use_nodejs_ui)

    # DSM / RTK detection
    if dsm_path:
        if not Path(dsm_path).is_file():
            logger.warning(f"{dsm_path} is not a valid DSM file. Switching to default elevation model.")
            config.update_dtm("")  # match previous behavior
        else:
            config.update_dtm(dsm_path)
    else:
        config.update_dtm("")

    # Detect RTK sidecar(s)
    rtk_exts = {".obs", ".mrk", ".bin", ".nav"}  # case-insensitive compare
    rtk_present = any(p.suffix.lower() in rtk_exts for p in indir.iterdir() if p.is_file())
    if rtk_present:
        config.update_rtk(True)

    # --- Collect images
    image_exts = {".jpg", ".jpeg", ".tif", ".tiff"}
    files = sorted(
        [p for p in indir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
        key=lambda x: int("".join(filter(str.isdigit, x.name))) if any(c.isdigit() for c in x.name) else x.name.lower()
    )
    logger.info(f"Found {len(files)} image files in the specified directory.")
    if not files:
        raise FileNotFoundError("No image files found in the specified directory.")

    # --- EXIF metadata
    exif_array: list[dict] = []
    with exiftool.ExifToolHelper() as et:
        exif_array.extend(et.get_metadata(files))
    if not exif_array:
        raise RuntimeError("Failed to extract metadata from image files.")
    logger.info(f"Metadata gathered for {len(files)} image files.")

    # --- Output dirs
    geojson_dir = outdir / "geojsons"
    geotiff_dir = outdir / "geotiffs"
    geojson_dir.mkdir(parents=True, exist_ok=True)
    geotiff_dir.mkdir(parents=True, exist_ok=True)

    # --- Sensor dimensions
    sensor_dimensions = read_sensor_dimensions_from_csv(sensor_info_csv, sensor_width_mm, sensor_height_mm)
    if sensor_dimensions is None:
        raise RuntimeError("Error reading sensor dimensions from CSV.")

    # --- Core processing
    feature_collection, images_array = process_metadata(
        exif_array, str(indir), geotiff_dir, sensor_dimensions
    )

    # --- Write GeoJSON
    geojson_file = f"M_{now.strftime('%Y-%m-%d_%H-%M')}.json"
    geojson_path = geojson_dir / geojson_file
    try:
        with open(geojson_path, "w") as f:
            geojson.dump(feature_collection, f, indent=4)
    except Exception as e:
        logger.critical(f"Error writing GeoJSON file: {e}")
        raise

    # --- Optional mosaic (when use_nodejs_ui=True, matching previous toggle)
    mosaic_dir = None
    if use_nodejs_ui:
        mosaic_dir = outdir / "mosaic"
        mosaic_dir.mkdir(parents=True, exist_ok=True)
        create_mosaic(str(indir), mosaic_dir)

    geo_type = "Cloud Optimized" if cog else "standard"
    logger.success(f"Process complete. {len(images_array)} {geo_type} GeoTIFFs and one GeoJSON were created.")
    logger.remove()  # clean up handlers

    return {
        "feature_collection": feature_collection,
        "geojson_path": geojson_path,
        "geotiff_dir": geotiff_dir,
        "mosaic_dir": mosaic_dir,
        "num_images": len(images_array),
        "log_path": log_path,
    }