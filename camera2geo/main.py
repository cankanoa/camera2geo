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
    """
    Convert raw camera or drone images to georeferenced GeoTIFFs. This function reads image EXIF metadata, determines camera geometry, and projects the image footprint into geographic space. A GeoTIFF is produced for each input image using ground elevation data from either a local DSM or an online elevation service.

    Args:
        input_images (str | List[str], required): Defines input files from a glob path, folder, or list of paths. Specify like: "/input/files/*.tif", "/input/folder" (assumes *.tif), ["/input/one.tif", "/input/two.tif"].
        output_images (str | List[str], required): Defines output files from a template path, folder, or list of paths (with the same length as the input). Specify like: "/input/files/$.tif", "/input/folder" (assumes $_Global.tif), ["/input/one.tif", "/input/two.tif"].
        sensor_width_mm: Sensor physical width in millimeters. If not provided, dimensions are inferred from the sensor info CSV.
        sensor_height_mm: Sensor physical height in millimeters. If not provided, dimensions are inferred from the sensor info CSV.
        epsg: EPSG code of the output coordinate reference system.
        correct_magnetic_declination: If True, adjust camera yaw using magnetic declination.
        cog: If True, create Cloud-Optimized GeoTIFF output.
        image_equalize: If True, apply histogram equalization.
        lens_correction: If True, apply lens distortion correction.
        elevation_data: Controls elevation source. If False, no elevation is used; if True, an online elevation service is queried; if a string, it is interpreted as a local DSM path.
        sensor_info_csv: CSV file containing known camera sensor dimensions with the following columns: DroneMake,DroneModel,CameraMake,SensorModel,RigCameraIndex,SensorWidth,SensorHeight,LensFOVw,LensFOVh
    """

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