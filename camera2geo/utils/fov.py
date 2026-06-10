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
)
from .elevation import ImageProjectionSolver
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
            utmx, utmy, _, _ = gps_to_utm(self.latitude, self.longitude)
            FOVw, FOVh = self.calculate_fov_dimensions()
            rotated_vectors = self.get_bounding_polygon(FOVw, FOVh)
            elevation_solver = ImageProjectionSolver(image, utmx, utmy)
            elevation_bbox = elevation_solver.solve(rotated_vectors)
            translated_bbox = find_geodetic_intersections(
                elevation_bbox, self.longitude, self.latitude
            )
            corrected_altitude = elevation_solver._atmospheric_refraction_correction(
                image.relative_altitude
            )
            self.image.center_distance = drone_distance_to_polygon_center(
                translated_bbox, (utmx, utmy), corrected_altitude
            )
            if self._has_extreme_edge_ratio(translated_bbox, factor=6):
                warnings.warn(
                    f"One side of the polygon for {image.file_name} is much longer than another."
                )
            return translate_to_wgs84(translated_bbox, self.longitude, self.latitude)

        except Exception as e:
            image.processing_error = (
                f"Footprint generation failed for {image.file_name}: {e}"
            )
            warnings.warn(image.processing_error)
            return None, None

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
