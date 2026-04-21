#  Copyright (c) 2024.
#  __author__ = "Dean Hand"
#  __license__ = "AGPL"
#  __version__ = "1.0"

import json
import warnings

from functools import lru_cache
from rasterio import rasterio
from rasterio.transform import rowcol
from urllib.request import urlopen
from urllib.error import HTTPError
from time import sleep

from .metadata import ImageClass

ATTEMPS_NUMBERS: int = 10


@lru_cache(maxsize=2)
def _load_local_elevation_data(dsm_path: str):
    with rasterio.open(dsm_path) as src:
        return src.read(1), src.crs, src.transform


def load_elevation_data_and_crs():
    if ImageClass.dsm_path is None:
        return None, None, None

    return _load_local_elevation_data(ImageClass.dsm_path)


def get_ground_elevation_at_point(x, y, image: ImageClass):
    elevation_data, _, affine_transform = load_elevation_data_and_crs()
    if elevation_data is None or affine_transform is None:
        return None

    row, col = rowcol(affine_transform, x, y)
    if 0 <= row < elevation_data.shape[0] and 0 <= col < elevation_data.shape[1]:
        return elevation_data[row, col]

    warnings.warn(
        f"Point ({x}, {y}) is outside the elevation data bounds for file {image.file_name}. Switching to default elevation."
    )
    return None


def get_relative_altitude_from_local_dem(x, y, image: ImageClass):
    ground_elevation = get_ground_elevation_at_point(x, y, image)
    if ground_elevation is None:
        return None

    return image.absolute_altitude - ground_elevation


def get_relative_altitude_from_ground_elevation(
    ground_elevation: float | None, image: ImageClass
):
    if ground_elevation is None:
        return None

    return image.absolute_altitude - ground_elevation


def get_ground_elevation_from_open(lat: float, long: float, image: ImageClass) -> float:
    """
    Get terrain elevation from open-elevation.com using input lat and long.
    """

    nb_of_failed_connection = 0
    while nb_of_failed_connection < ATTEMPS_NUMBERS:
        try:
            url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{long}"
            with urlopen(url) as response:
                data = response.read().decode("utf-8")
            elevation = json.loads(data)["results"][0]["elevation"]
            print(
                f"Successfull connection to OpenElevation for file{image.file_name} with coordinates {lat},{long}"
            )
            return elevation
        except HTTPError as err:
            warnings.warn(
                f"Connexion error for OpenElevation file:{image.file_name} coordinates {lat},{long}. Error: {err}"
            )
            nb_of_failed_connection += 1
            # Sleep random time before next try
            sleep(nb_of_failed_connection)
    print(
        f"Too many failures for file {image.file_name}. Switching to default elevation."
    )
    return None


def get_relative_altitude_from_open(lat: float, long: float, image: ImageClass) -> float:
    ground_elevation = get_ground_elevation_from_open(lat, long, image)
    if ground_elevation is None:
        return None

    return image.absolute_altitude - ground_elevation


def get_ground_elevations_from_open(
    latlon_tupples: list[tuple], image: ImageClass
) -> list[float]:
    """
    Get terrain elevations from open-elevation.com for a list of latitude/longitude tuples.
    """
    url_coordinates = ""
    nb_of_coordinates = 0
    # Prepare url values
    for coordinates in latlon_tupples:
        url_coordinates += f"{coordinates[0]},{coordinates[1]}|"
        nb_of_coordinates += 1
    # remove last |
    url_coordinates = url_coordinates.rstrip("|")

    nb_of_failed_connection = 0
    while nb_of_failed_connection < ATTEMPS_NUMBERS:
        try:
            url = f"https://api.open-elevation.com/api/v1/lookup?locations={url_coordinates}"
            with urlopen(url) as response:
                data = response.read().decode("utf-8")

            print(
                f"Successfull connection to OpenElevation for file {image.file_name} with coordinates {latlon_tupples}"
            )
            return [result["elevation"] for result in json.loads(data)["results"]]
        except HTTPError as err:
            warnings.warn(
                f"Unable to Connect to OpenElevation for file {image.file_name} with coordinates {latlon_tupples}. Error: {err}"
            )
            nb_of_failed_connection += 1
            # Sleep random time before next try
            sleep(nb_of_failed_connection)
    print(
        f"Too many failures for file {image.file_name}. Switching to default elevation."
    )
    return None


def get_relative_altitudes_from_open(
    latlon_tupples: list[tuple], image: ImageClass
) -> list[float]:
    ground_elevations = get_ground_elevations_from_open(latlon_tupples, image)
    if ground_elevations is None:
        return None

    return [image.absolute_altitude - elevation for elevation in ground_elevations]
