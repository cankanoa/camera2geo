#  Copyright (c) 2024.
#  __author__ = "Dean Hand"
#  __license__ = "AGPL"
#  __version__ = "1.0"

from scipy.spatial.transform import Rotation as R
import warnings

from mpmath import mp, radians, sqrt
from vector3d.vector import Vector

from .geospatial import (
    find_geodetic_intersections,
    gps_to_utm,
    translate_to_wgs84,
    utm_to_latlon,
)
from .elevation import (
    get_ground_elevation_at_point,
    get_relative_altitude_from_ground_elevation,
    get_relative_altitude_from_local_dem,
    get_relative_altitude_from_open,
    get_relative_altitudes_from_open,
)
from .metadata import ImageClass


class FOVCalculator:
    def __init__(self, image: ImageClass):
        mp.dps = 50  # set a higher precision
        self.image = image
        self.drone_gps = (image.latitude, image.longitude)
        self.latitude = image.latitude
        self.longitude = image.longitude

    def calculate_fov_dimensions(self):
        FOVw = 2 * mp.atan(
            mp.mpf(self.image.sensor_width) / (2 * self.image.focal_length)
        )
        FOVh = 2 * mp.atan(
            mp.mpf(self.image.sensor_height) / (2 * self.image.focal_length)
        )

        # _sensor_lens_correction now inside this function
        corrected_fov_width = FOVw * self.image.lens_FOV_width
        corrected_fov_height = FOVh * self.image.lens_FOV_height

        return corrected_fov_width, corrected_fov_height

    @staticmethod
    def calculate_rads_from_angles(
        gimbal_yaw_deg, gimbal_pitch_deg, gimbal_roll_deg, declination
    ):
        """
        Adjusts the gimbal's angles for magnetic declination and normalizes the roll orientation.
        - Yaw is adjusted for magnetic declination.
        - Roll is normalized if within a specific range to handle edge cases around 90 degrees.
        - Pitch is converted directly to radians.

        Parameters:
        - gimbal_yaw_deg (float): The gimbal's yaw angle in degrees.
        - gimbal_pitch_deg (float): The gimbal's pitch angle in degrees.
        - gimbal_roll_deg (float): The gimbal's roll angle in degrees.
        - declination (float): Magnetic declination in degrees.

        Returns:
        - tuple: Adjusted yaw, pitch, and roll angles in radians.
        """
        # Normalize yaw for magnetic declination
        if -120 <= gimbal_pitch_deg <= -60:
            pitch_rad = radians(90 - gimbal_pitch_deg)
        else:
            pitch_rad = radians(180 - gimbal_pitch_deg)

        if ImageClass.correct_magnetic_declination:
            yaw_rad = (mp.pi / 2) - radians(gimbal_yaw_deg + declination)
        else:
            yaw_rad = (mp.pi / 2) - radians(gimbal_yaw_deg)
        yaw_rad = yaw_rad % (2 * mp.pi)
        roll_rad = radians(gimbal_roll_deg)

        return yaw_rad, pitch_rad, roll_rad

    def get_bounding_polygon(self, fov_width, fov_height):
        """
        Calculates the bounding polygon of a camera's footprint given its field of view, position, and orientation.

        Parameters:
            FOVh (float): The horizontal field of view in radians.
            FOVv (float): The vertical field of view in radians.
            altitude (float): The altitude above ground in meters.
            roll (float): The roll angle in radians.
            pitch (float): The pitch angle in radians.
            yaw (float): The yaw angle in radians.

        Returns:
            list: A list of Vector objects representing the corners of the bounding polygon on the ground.
        """

        # Define camera rays based on field of view
        rays = [
            Vector(
                -mp.tan(fov_height / 2), mp.tan(fov_width / 2), 1
            ).normalize(),  # Flip horizontally
            Vector(
                -mp.tan(fov_height / 2), -mp.tan(fov_width / 2), 1
            ).normalize(),  # Flip horizontally
            Vector(
                mp.tan(fov_height / 2), -mp.tan(fov_width / 2), 1
            ).normalize(),  # Flip horizontally
            Vector(
                mp.tan(fov_height / 2), mp.tan(fov_width / 2), 1
            ).normalize(),  # Flip horizontally
        ]
        # Rotate rays according to camera orientation
        rotated_vectors = self.rotate_rays(rays)

        return rotated_vectors

    def rotate_rays(self, rays):
        # Calculate adjusted angles for gimbal and flight orientations
        self.image.find_declination()
        declination = self.image.declination

        adj_yaw, adj_pitch, adj_roll = self.calculate_rads_from_angles(
            self.image.gimbal_yaw_degree,
            self.image.gimbal_pitch_degree,
            self.image.gimbal_roll_degree,
            declination,
        )

        # Match the old quaternion from_euler_angles convention (Z–Y–Z style)
        r = R.from_euler(
            "ZYZ",
            [float(adj_yaw), float(adj_pitch), float(adj_roll)],
            degrees=False,
        )

        rotated = r.apply([(float(ray.x), float(ray.y), float(ray.z)) for ray in rays])
        return [Vector(*vec) for vec in rotated]

    def get_fov_bbox(self, image: ImageClass):
        try:
            utmx, utmy, zone_number, zone_letter = gps_to_utm(
                self.latitude, self.longitude
            )
            image.set_relative_altitude(self._resolve_relative_altitude(utmx, utmy))
            corrected_altitude = self._atmospheric_refraction_correction(
                image.relative_altitude
            )
            FOVw, FOVh = self.calculate_fov_dimensions()
            rotated_vectors = self.get_bounding_polygon(FOVw, FOVh)

            elevation_bbox = FOVCalculator.get_ray_ground_intersections(
                rotated_vectors, Vector(0, 0, float(corrected_altitude))
            )
            translated_bbox = find_geodetic_intersections(
                elevation_bbox, self.longitude, self.latitude
            )
            self.image.center_distance = drone_distance_to_polygon_center(
                translated_bbox, (utmx, utmy), corrected_altitude
            )
            if ImageClass.elevation_mode == "local":
                altitudes = self._get_local_polygon_altitudes(translated_bbox, image)
                if altitudes is None:
                    warnings.warn(
                        f"Failed to get elevation for image {image.file_name}. See log for details."
                    )
                    return translate_to_wgs84(
                        translated_bbox, self.longitude, self.latitude
                    )
                if self._has_extreme_edge_ratio(translated_bbox, factor=6):
                    warnings.warn(
                        f"One side of the polygon for {image.file_name} is at least 5 times longer than another."
                    )
                    return translate_to_wgs84(
                        translated_bbox, self.longitude, self.latitude
                    )

            elif ImageClass.elevation_mode == "online":
                trans_utmbox = [
                    utm_to_latlon(box[0], box[1], zone_number, zone_letter)
                    for box in translated_bbox
                ]
                altitudes = get_relative_altitudes_from_open(trans_utmbox, image)

                if altitudes is None or None in altitudes:
                    warnings.warn(
                        f"Failed to get elevation at point for {image.file_name}."
                    )
                    return translate_to_wgs84(
                        translated_bbox, self.longitude, self.latitude
                    )
                if self._has_extreme_edge_ratio(translated_bbox, factor=5):
                    warnings.warn(
                        f"One side of the polygon for {image.file_name} is at least 5 times longer than another."
                    )
                    return translate_to_wgs84(
                        translated_bbox, self.longitude, self.latitude
                    )

            # If no special conditions are met, process normally
            return translate_to_wgs84(translated_bbox, self.longitude, self.latitude)

        except Exception as e:
            warnings.warn(f"Error in get_fov_bbox: {e}")
            return None, None

    def _resolve_relative_altitude(self, utmx: float, utmy: float) -> float:
        if ImageClass.elevation_mode == "plane":
            return self.image.metadata_relative_altitude

        if ImageClass.elevation_mode == "local":
            relative_altitude = get_relative_altitude_from_local_dem(
                utmx, utmy, self.image
            )
            if relative_altitude is not None:
                return relative_altitude
            warnings.warn(
                f"Failed to compute relative altitude from local elevation for {self.image.file_name}, using absolute altitude."
            )
            return self.image.absolute_altitude

        if ImageClass.elevation_mode == "online":
            relative_altitude = get_relative_altitude_from_open(
                self.image.latitude, self.image.longitude, self.image
            )
            if relative_altitude is not None:
                return relative_altitude
            warnings.warn(
                f"Failed to compute relative altitude from online elevation for {self.image.file_name}, using absolute altitude."
            )
            return self.image.absolute_altitude

        return self.image.metadata_relative_altitude

    def _get_local_polygon_altitudes(self, bbox, image: ImageClass):
        altitudes = []
        for x, y in bbox:
            ground_elevation = get_ground_elevation_at_point(x, y, image)
            relative_altitude = get_relative_altitude_from_ground_elevation(
                ground_elevation, image
            )
            if relative_altitude is None:
                return None
            altitudes.append(relative_altitude)
        return altitudes

    @staticmethod
    def _has_extreme_edge_ratio(bbox, factor: int):
        distances = [
            sqrt(
                (bbox[(i + 1) % len(bbox)][0] - point[0]) ** 2
                + (bbox[(i + 1) % len(bbox)][1] - point[1]) ** 2
            )
            for i, point in enumerate(bbox)
        ]
        return any(
            other_distance * factor < distance
            for distance in distances
            for other_distance in distances
            if other_distance != distance
        )

    @staticmethod
    def get_ray_ground_intersections(rays, origin):
        """
        Calculates the intersection points of the given rays with the ground plane.

        Parameters:
            rays (list): A list of Vector objects representing the rays.
            origin (Vector): The origin point of the rays.

        Returns:
            list: A list of Vector objects representing the intersection points on the ground.
        """

        intersections = []
        for ray in rays:
            intersection = FOVCalculator.find_ray_ground_intersection(ray, origin)
            if intersection is not None:
                intersections.append(intersection)

        return intersections

    @staticmethod
    def find_ray_ground_intersection(ray, origin):
        """
        Finds the intersection point of a single ray with the ground plane.

        Parameters:
            ray (Vector): The ray vector.
            origin (Vector): The origin point of the ray.

        Returns:
            Vector: The intersection point with the ground, or None if the ray is parallel to the ground.
        """

        if ray.z == 0:  # Ray is parallel to ground
            return None

        # Calculate intersection parameter t
        t = -origin.z / ray.z
        return Vector(origin.x + ray.x * t, origin.y + ray.y * t, 0)

    def _atmospheric_refraction_correction(self, altitude):
        return altitude + (altitude * 0.0001)


def calculate_centroid(polygon_coords):
    """Calculate the centroid of a polygon given its vertices in UTM coordinates."""
    x_sum = 0
    y_sum = 0
    for x, y in polygon_coords:
        x_sum += x
        y_sum += y
    centroid = (x_sum / len(polygon_coords), y_sum / len(polygon_coords))
    return centroid


def distance_3d(point1, point2):
    """Calculate the 3D distance between two points in UTM coordinates."""
    return sqrt(
        (point1[0] - point2[0]) ** 2
        + (point1[1] - point2[1]) ** 2
        + (point1[2] - point2[2]) ** 2
    )


def drone_distance_to_polygon_center(polygon_coords, drone_coords, drone_altitude):
    """
    Calculate the distance from a drone to the center of a polygon in UTM coordinates.

    Parameters:
    - polygon_coords: list of tuples, each representing the (x, y) UTM coordinates of a polygon's vertex.
    - drone_coords: Tuple representing the (x, y) UTM coordinates of the drone's location.
    - drone_altitude: Float representing the drone's altitude in meters above the ground.

    Returns:
    - Float: The distance from the drone to the centroid of the polygon.
    """
    # Calculate the centroid of the polygon
    centroid = calculate_centroid(polygon_coords)
    centroid_3d = (centroid[0], centroid[1], 0)
    drone_position_3d = (drone_coords[0], drone_coords[1], drone_altitude)
    center_distance = distance_3d(centroid_3d, drone_position_3d)
    return center_distance
