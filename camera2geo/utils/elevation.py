import math
import warnings

from functools import lru_cache

import rasterio
from rasterio.transform import rowcol
from pyproj import Transformer
from vector3d.vector import Vector

from .geospatial import get_utm_crs
from .metadata import ImageClass


@lru_cache(maxsize=2)
def _load_local_elevation_data(dsm_path: str):
    with rasterio.open(dsm_path) as src:
        return src.read(1), src.crs, src.transform, src.nodata


def load_elevation_data_and_crs():
    if ImageClass.elevation_file is None:
        return None, None, None, None

    return _load_local_elevation_data(ImageClass.elevation_file)


@lru_cache(maxsize=16)
def _get_dem_point_transformer(
    latitude: float, longitude: float, dem_crs_wkt: str
) -> Transformer:
    source_crs = get_utm_crs(latitude, longitude)
    return Transformer.from_crs(source_crs, dem_crs_wkt, always_xy=True)


def _transform_point_to_dem_crs(x: float, y: float, image: ImageClass, dem_crs):
    if dem_crs is None or not ImageClass.reproject_elevation_point:
        return x, y

    transformer = _get_dem_point_transformer(
        image.latitude, image.longitude, dem_crs.to_wkt()
    )
    transformed_x, transformed_y = transformer.transform(x, y)
    return float(transformed_x), float(transformed_y)


class ImageProjectionSolver:
    def __init__(self, image: ImageClass, drone_utmx: float, drone_utmy: float):
        self.image = image
        self.drone_utmx = drone_utmx
        self.drone_utmy = drone_utmy

    def solve(self, rays: list[Vector]) -> list[Vector]:
        if ImageClass.projection_mode == "point":
            return self.point(rays)
        if ImageClass.projection_mode == "mesh":
            return self.mesh(rays)
        raise ValueError(f"Unsupported projection mode: {ImageClass.projection_mode}")

    def point(self, rays: list[Vector]) -> list[Vector]:
        relative_altitude = get_relative_altitude_from_local_dem(
            self.drone_utmx, self.drone_utmy, self.image
        )
        if relative_altitude is None:
            warnings.warn(
                f"Failed to compute relative altitude from elevation surface for {self.image.file_name}, using absolute altitude."
            )
            relative_altitude = self.image.absolute_altitude
        return self._intersections_on_flat_plane(rays, relative_altitude)

    def mesh(self, rays: list[Vector]) -> list[Vector]:
        camera_ground_elevation = get_ground_elevation_at_point(
            self.drone_utmx, self.drone_utmy, self.image
        )
        if camera_ground_elevation is None:
            warnings.warn(
                f"Failed to read terrain at the camera location for {self.image.file_name}, falling back to point projection."
            )
            return self.point(rays)

        relative_altitude = get_relative_altitude_from_ground_elevation(
            camera_ground_elevation, self.image
        )
        if relative_altitude is None:
            warnings.warn(
                f"Failed to compute relative altitude from terrain for {self.image.file_name}, falling back to point projection."
            )
            return self.point(rays)

        self.image.set_relative_altitude(relative_altitude)
        corrected_altitude = self._atmospheric_refraction_correction(relative_altitude)
        origin = Vector(0, 0, float(corrected_altitude))
        intersections = []
        for ray in rays:
            intersection = self._find_ray_mesh_intersection(
                ray=ray,
                origin=origin,
                camera_ground_elevation=float(camera_ground_elevation),
            )
            if intersection is None:
                warnings.warn(
                    f"Failed to intersect image ray with terrain mesh for {self.image.file_name}, falling back to point projection."
                )
                return self.point(rays)
            intersections.append(intersection)
        return intersections

    def _intersections_on_flat_plane(
        self, rays: list[Vector], relative_altitude: float
    ) -> list[Vector]:
        self.image.set_relative_altitude(relative_altitude)
        corrected_altitude = self._atmospheric_refraction_correction(relative_altitude)
        origin = Vector(0, 0, float(corrected_altitude))
        intersections = []
        for ray in rays:
            intersection = self._find_ray_ground_intersection(ray, origin)
            if intersection is not None:
                intersections.append(intersection)
        return intersections

    def _find_ray_mesh_intersection(
        self, ray: Vector, origin: Vector, camera_ground_elevation: float
    ) -> Vector | None:
        if ray.z >= 0:
            return None

        plane_intersection = self._find_ray_ground_intersection(ray, origin)
        if plane_intersection is None:
            return None

        plane_distance = math.hypot(
            float(plane_intersection.x), float(plane_intersection.y)
        )
        max_distance = max(plane_distance * 1.5, origin.z * 1.25, 10.0)
        horizontal_magnitude = math.hypot(float(ray.x), float(ray.y))
        if horizontal_magnitude == 0:
            return None

        step_distance = min(max(origin.z / 20.0, 2.0), 25.0)
        step_t = step_distance / horizontal_magnitude
        max_t = max_distance / horizontal_magnitude

        previous_t = 0.0
        previous_delta = self._terrain_delta(previous_t, ray, origin, camera_ground_elevation)
        if previous_delta is None:
            return None
        if previous_delta <= 0:
            return origin

        current_t = step_t
        while current_t <= max_t:
            current_delta = self._terrain_delta(
                current_t, ray, origin, camera_ground_elevation
            )
            if current_delta is None:
                return None
            if current_delta <= 0:
                hit_t = self._refine_hit_t(
                    low_t=previous_t,
                    high_t=current_t,
                    ray=ray,
                    origin=origin,
                    camera_ground_elevation=camera_ground_elevation,
                )
                return Vector(
                    origin.x + ray.x * hit_t,
                    origin.y + ray.y * hit_t,
                    origin.z + ray.z * hit_t,
                )
            previous_t = current_t
            previous_delta = current_delta
            current_t += step_t

        return None

    def _refine_hit_t(
        self,
        *,
        low_t: float,
        high_t: float,
        ray: Vector,
        origin: Vector,
        camera_ground_elevation: float,
    ) -> float:
        for _ in range(20):
            mid_t = (low_t + high_t) / 2.0
            mid_delta = self._terrain_delta(
                mid_t, ray, origin, camera_ground_elevation
            )
            if mid_delta is None:
                return low_t
            if mid_delta > 0:
                low_t = mid_t
            else:
                high_t = mid_t
        return high_t

    def _terrain_delta(
        self, t: float, ray: Vector, origin: Vector, camera_ground_elevation: float
    ) -> float | None:
        sample_x = self.drone_utmx + float(origin.x + ray.x * t)
        sample_y = self.drone_utmy + float(origin.y + ray.y * t)
        ground_elevation = get_ground_elevation_at_point(sample_x, sample_y, self.image)
        if ground_elevation is None:
            return None
        terrain_z = float(ground_elevation) - camera_ground_elevation
        ray_z = float(origin.z + ray.z * t)
        return ray_z - terrain_z

    @staticmethod
    def _find_ray_ground_intersection(ray: Vector, origin: Vector) -> Vector | None:
        if ray.z == 0:
            return None
        t = -origin.z / ray.z
        if t < 0:
            return None
        return Vector(origin.x + ray.x * t, origin.y + ray.y * t, 0)

    @staticmethod
    def _atmospheric_refraction_correction(altitude: float) -> float:
        return altitude + (altitude * 0.0001)


def get_ground_elevation_at_point(x, y, image: ImageClass):
    elevation_data, dem_crs, affine_transform, nodata_value = load_elevation_data_and_crs()
    if elevation_data is None or affine_transform is None:
        return None

    sample_x, sample_y = _transform_point_to_dem_crs(x, y, image, dem_crs)

    row, col = rowcol(affine_transform, sample_x, sample_y)
    if 0 <= row < elevation_data.shape[0] and 0 <= col < elevation_data.shape[1]:
        value = float(elevation_data[row, col])
        if nodata_value is not None and math.isclose(value, float(nodata_value)):
            warnings.warn(
                f"Point ({sample_x}, {sample_y}) falls on DEM nodata for file {image.file_name}."
            )
            return None
        return value

    warnings.warn(
        f"Point ({sample_x}, {sample_y}) is outside the elevation data bounds for file {image.file_name}."
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
