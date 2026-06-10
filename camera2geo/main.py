import os
import warnings

from pathlib import Path
from typing import Callable, List

from .utils.io import read_sensor_dimensions_from_csv, _resolve_paths
from .utils.metadata_reader import read_metadata_batch
from .utils.metadata import ImageClass
from .utils.fov import FOVCalculator
from .utils.opentopo import download_opentopo_dem
from .utils.raster_utils import generate_geotiff


VALID_PROJECTION_MODES = {"point", "mesh"}
VALID_ELEVATION_SURFACES = {"local_file", "opentopo_extent"}


def _resolve_surface_inputs(
    projection: str,
    elevation_surface: str,
    elevation_file: str | None,
    opentopo_extent: str | tuple[float, float, float, float] | None,
    opentopo_api_key: str | None,
    opentopo_cache_file: str | None,
    default_cache_file: str,
):
    if projection not in VALID_PROJECTION_MODES:
        raise ValueError(
            f"projection must be one of {sorted(VALID_PROJECTION_MODES)}."
        )
    if elevation_surface not in VALID_ELEVATION_SURFACES:
        raise ValueError(
            "elevation_surface must be one of "
            f"{sorted(VALID_ELEVATION_SURFACES)}."
        )

    resolved_elevation_file = elevation_file
    if elevation_surface == "local_file":
        if not elevation_file:
            raise ValueError(
                "elevation_file is required when elevation_surface='local_file'."
            )
    else:
        if not opentopo_extent:
            raise ValueError(
                "opentopo_extent is required when elevation_surface='opentopo_extent'."
            )
        if not opentopo_api_key:
            raise ValueError(
                "opentopo_api_key is required when elevation_surface='opentopo_extent'."
            )
        resolved_elevation_file = download_opentopo_dem(
            extent_4326=opentopo_extent,
            api_key=opentopo_api_key,
            output_path=opentopo_cache_file or default_cache_file,
        )

    return projection, elevation_surface, resolved_elevation_file


def _configure_image_class(
    *,
    epsg: int,
    correct_magnetic_declination: bool,
    cog: bool,
    image_equalize: bool,
    lens_correction: bool,
    projection_mode: str,
    elevation_surface: str,
    elevation_file: str | None,
    reproject_elevation_point: bool,
    no_data_value: float | int,
    replace_nodata_value: float | int | None,
):
    ImageClass.epsg = epsg
    ImageClass.correct_magnetic_declination = correct_magnetic_declination
    ImageClass.cog = cog
    ImageClass.image_equalize = image_equalize
    ImageClass.lens_correction = lens_correction
    ImageClass.projection_mode = projection_mode
    ImageClass.elevation_surface = elevation_surface
    ImageClass.elevation_file = elevation_file
    ImageClass.reproject_elevation_point = reproject_elevation_point
    ImageClass.no_data_value = no_data_value
    ImageClass.replace_nodata_value = replace_nodata_value


def _report_progress(progress_callback: Callable[[float], None] | None, value: float):
    if progress_callback is not None:
        progress_callback(value)


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
    projection: str = "point",
    elevation_surface: str = "local_file",
    elevation_file: str | None = None,
    opentopo_extent: str | tuple[float, float, float, float] | None = None,
    opentopo_api_key: str | None = None,
    opentopo_cache_file: str | None = None,
    reproject_elevation_point: bool = True,
    no_data_value: float | int = 0,
    replace_nodata_value: float | int | None = 1,
    progress_callback: Callable[[float], None] | None = None,
    sensor_info_csv: str = f"{os.path.dirname(os.path.abspath(__file__))}/sensors.csv",
) -> list:
    """
    Convert raw camera or drone images to georeferenced GeoTIFFs. This function reads image EXIF metadata, determines camera geometry, and projects the image footprint into geographic space. A GeoTIFF is produced for each input image using a projection mode (`point` or `mesh`) and an elevation surface (`local_file` or `opentopo_extent`).

    Args:
        input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.JPG", "/input/folder" (assumes *.JPG), ["/input/one.JPG", "/input/two.JPG"].
        output_images (str | List[str], required): Defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Geo.tif), ["/input/one.tif", "/input/two.tif"].
        sensor_width_mm: Sensor physical width in millimeters. If not provided, dimensions are inferred from the sensor info CSV.
        sensor_height_mm: Sensor physical height in millimeters. If not provided, dimensions are inferred from the sensor info CSV.
        epsg: EPSG code of the output coordinate reference system.
        correct_magnetic_declination: If True, adjust camera yaw using magnetic declination.
        cog: If True, create Cloud-Optimized GeoTIFF output.
        image_equalize: If True, apply histogram equalization.
        lens_correction: If True, apply lens distortion correction.
        projection: Projection mode. Use `point` for camera-point elevation against a flat plane or `mesh` for full ray intersection against the elevation surface.
        elevation_surface: Elevation surface source. Use `local_file` for a supplied raster path or `opentopo_extent` to download an OpenTopography raster for a WGS84 bounding box.
        elevation_file: Local elevation raster path when `elevation_surface='local_file'`.
        opentopo_extent: WGS84 bounding box as `(west, south, east, north)` or `"west,south,east,north"` when `elevation_surface='opentopo_extent'`.
        opentopo_api_key: OpenTopography API key when `elevation_surface='opentopo_extent'`.
        opentopo_cache_file: Optional raster path used to store the downloaded OpenTopography surface. If omitted, a cache file is created beside the first output raster.
        reproject_elevation_point: If True, transform sampled point coordinates from the image UTM CRS into the elevation raster CRS before reading heights.
        no_data_value: Pixel value used to fill empty warped areas and written as the output GeoTIFF nodata value.
        replace_nodata_value: If provided, replace source pixels equal to no_data_value before warping so those pixels are preserved as regular image data.
        progress_callback: Optional callback receiving progress values from 0-100.
        sensor_info_csv: CSV file containing known camera sensor dimensions with the following columns: DroneMake,DroneModel,CameraMake,SensorModel,RigCameraIndex,SensorWidth,SensorHeight,LensFOVw,LensFOVh
    """

    print(f"Run camera2geo on {input_images} to {output_images}")

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

    default_cache_file = str(
        Path(output_image_paths[0]).parent / "_camera2geo_opentopo_surface.tif"
    )
    projection_mode, elevation_surface, elevation_file = _resolve_surface_inputs(
        projection,
        elevation_surface,
        elevation_file,
        opentopo_extent,
        opentopo_api_key,
        opentopo_cache_file,
        default_cache_file,
    )
    _configure_image_class(
        epsg=epsg,
        correct_magnetic_declination=correct_magnetic_declination,
        cog=cog,
        image_equalize=image_equalize,
        lens_correction=lens_correction,
        projection_mode=projection_mode,
        elevation_surface=elevation_surface,
        elevation_file=elevation_file,
        reproject_elevation_point=reproject_elevation_point,
        no_data_value=no_data_value,
        replace_nodata_value=replace_nodata_value,
    )
    _report_progress(progress_callback, 5)

    exif_array = read_metadata_batch([str(path) for path in input_image_paths])
    _report_progress(progress_callback, 20)

    # Load camera sensor specs
    sensor_dimensions = read_sensor_dimensions_from_csv(
        sensor_info_csv, sensor_width_mm, sensor_height_mm
    )

    # Output folders exist
    for p in output_image_paths:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    produced_paths = []
    failure_messages = []
    total_images = max(len(exif_array), 1)

    # Set per image
    for index, (exif, in_path, out_path) in enumerate(
        zip(exif_array, input_image_paths, output_image_paths), start=1
    ):
        start_progress = 20 + ((index - 1) / total_images) * 80
        end_progress = 20 + (index / total_images) * 80
        _report_progress(progress_callback, start_progress)

        # Create per-image object
        image = ImageClass(
            metadata=exif,
            sensor_dimensions=sensor_dimensions,
        )

        # Compute FOV footprint & bounding box
        fov = FOVCalculator(image)
        image.coord_array, image.footprint_coordinates = fov.get_fov_bbox(image)
        if image.coord_array is None or image.footprint_coordinates is None:
            failure_message = (
                image.processing_error
                or f"Skipping {image.file_name} because footprint generation failed."
            )
            warnings.warn(failure_message)
            failure_messages.append(failure_message)
            _report_progress(progress_callback, end_progress)
            continue

        # Generate GeoTIFF
        write_success, write_error = generate_geotiff(
            self=image,
            input_dir=str(Path(in_path).parent),
            output_dir=str(Path(out_path).parent),
            output_path=str(out_path),
        )
        if not write_success:
            failure_message = (
                write_error
                or f"GeoTIFF writing failed for {image.file_name}."
            )
            warnings.warn(failure_message)
            failure_messages.append(failure_message)
            _report_progress(progress_callback, end_progress)
            continue

        produced_paths.append(str(out_path))
        _report_progress(progress_callback, end_progress)

    _report_progress(progress_callback, 100)
    if not produced_paths and failure_messages:
        raise RuntimeError(failure_messages[0])
    return produced_paths
