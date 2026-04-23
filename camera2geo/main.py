import os
import warnings

from pathlib import Path
from typing import Callable, List

from .utils.io import read_sensor_dimensions_from_csv, _resolve_paths
from .utils.metadata_reader import read_metadata_batch
from .utils.metadata import ImageClass
from .utils.fov import FOVCalculator
from .utils.raster_utils import generate_geotiff


def _resolve_elevation_mode(elevation_data: str | bool):
    if elevation_data is False:
        return "plane", None
    if elevation_data is True:
        return "online", None
    if isinstance(elevation_data, str):
        return "local", elevation_data

    raise ValueError(
        "elevation_data must be False, True, or a filesystem path string."
    )


def _configure_image_class(
    *,
    epsg: int,
    correct_magnetic_declination: bool,
    cog: bool,
    image_equalize: bool,
    lens_correction: bool,
    elevation_mode: str,
    dsm_path: str | None,
    no_data_value: float | int,
    replace_nodata_value: float | int | None,
):
    ImageClass.epsg = epsg
    ImageClass.correct_magnetic_declination = correct_magnetic_declination
    ImageClass.cog = cog
    ImageClass.image_equalize = image_equalize
    ImageClass.lens_correction = lens_correction
    ImageClass.elevation_mode = elevation_mode
    ImageClass.dsm_path = dsm_path
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
    elevation_data: str | bool = True,
    no_data_value: float | int = 0,
    replace_nodata_value: float | int | None = 1,
    progress_callback: Callable[[float], None] | None = None,
    sensor_info_csv: str = f"{os.path.dirname(os.path.abspath(__file__))}/sensors.csv",
) -> list:
    """
    Convert raw camera or drone images to georeferenced GeoTIFFs. This function reads image EXIF metadata, determines camera geometry, and projects the image footprint into geographic space. A GeoTIFF is produced for each input image using either the metadata relative altitude, a local DSM, or an online elevation service.

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
        elevation_data: Controls elevation source. If False, use the image metadata relative altitude as a flat plane. If True, query an online elevation service and compute relative altitude from the absolute altitude. If a string, interpret it as a local DSM path and compute relative altitude from the absolute altitude.
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

    elevation_mode, dsm_path = _resolve_elevation_mode(elevation_data)
    _configure_image_class(
        epsg=epsg,
        correct_magnetic_declination=correct_magnetic_declination,
        cog=cog,
        image_equalize=image_equalize,
        lens_correction=lens_correction,
        elevation_mode=elevation_mode,
        dsm_path=dsm_path,
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
            warnings.warn(
                f"Skipping {image.file_name} because footprint generation failed."
            )
            _report_progress(progress_callback, end_progress)
            continue

        # Generate GeoTIFF
        generate_geotiff(
            self=image,
            input_dir=str(Path(in_path).parent),
            output_dir=str(Path(out_path).parent),
            output_path=str(out_path),
        )

        produced_paths.append(str(out_path))
        _report_progress(progress_callback, end_progress)

    _report_progress(progress_callback, 100)
    return produced_paths
