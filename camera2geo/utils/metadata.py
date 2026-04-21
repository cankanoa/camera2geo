import warnings
import magnetismi.magnetismi as api

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import ClassVar
from datetime import datetime
from magnetic_field_calculator import MagneticFieldCalculator
from shapely.geometry import Polygon, mapping
from shapely.geometry.polygon import orient


@dataclass
class ImageMetadata:
    file_name: str
    latitude: float
    longitude: float
    gps_altitude: float | None
    focal_length: float
    focal_length35mm: float | None
    relative_altitude: float | None
    absolute_altitude: float | None
    gimbal_roll_degree: float
    gimbal_pitch_degree: float
    gimbal_yaw_degree: float
    flight_pitch_degree: float
    flight_roll_degree: float
    flight_yaw_degree: float
    image_width: int
    image_height: int
    max_aperture_value: float | None
    datetime_original: str | None
    sensor_model_data: str | None
    sensor_index: str
    sensor_make: str | None
    raw_metadata: dict = field(default_factory=dict)

    @property
    def metadata_relative_altitude(self) -> float:
        return float(self.relative_altitude or self.gps_altitude or 0.0)

    @property
    def metadata_absolute_altitude(self) -> float:
        return float(self.absolute_altitude or self.gps_altitude or 0.0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ImageClass:
    # Class vars
    epsg: ClassVar[int] = 4326
    correct_magnetic_declination: ClassVar[bool] = False
    cog: ClassVar[bool] = False
    image_equalize: ClassVar[bool] = False
    lens_correction: ClassVar[bool] = False
    elevation_mode: ClassVar[str] = "plane"
    dsm_path: ClassVar[str | None] = None
    no_data_value: ClassVar[float | int] = 0
    replace_nodata_value: ClassVar[float | int | None] = 1

    # Instance vars
    metadata: ImageMetadata
    sensor_dimensions: dict
    declination: float = None
    drone_hash: int = None
    feature_point: dict = field(default_factory=dict)
    feature_polygon: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)
    coord_array: list = field(default_factory=list)
    footprint_coordinates: list = field(default_factory=list)
    image_path: str = ""
    output_file: str = ""
    geotiff_file: str = ""
    def __post_init__(self):
        self.file_name = self.metadata.file_name

        # Extract detailed sensor and drone info for the current image
        # Extracting latitude, longitude, and altitude details
        self.latitude = self.metadata.latitude
        self.longitude = self.metadata.longitude
        self.focal_length = self.metadata.focal_length
        self.focal_length35mm = self.metadata.focal_length35mm

        self.relative_altitude = self.metadata.metadata_relative_altitude
        self.absolute_altitude = self.metadata.metadata_absolute_altitude

        # Extracting gimbal and flight orientation details
        self.gimbal_roll_degree = self.metadata.gimbal_roll_degree
        self.gimbal_pitch_degree = self.metadata.gimbal_pitch_degree
        self.gimbal_yaw_degree = self.metadata.gimbal_yaw_degree

        self.flight_pitch_degree = self.metadata.flight_pitch_degree
        self.flight_roll_degree = self.metadata.flight_roll_degree
        self.flight_yaw_degree = self.metadata.flight_yaw_degree

        # Extracting image and sensor details
        self.image_width = self.metadata.image_width  # pixels
        self.image_height = self.metadata.image_height  # pixels
        self.max_aperture_value = self.metadata.max_aperture_value
        # date/time of original image capture
        self.datetime_original = self.metadata.datetime_original
        # Get sensor model and rig camera index from metadata
        self.sensor_model_data = self.metadata.sensor_model_data
        self.sensor_index = self.metadata.sensor_index
        self.sensor_make = self.metadata.sensor_make or ""

        if self.sensor_model_data:
            # Prioritize direct match with sensor model and rig camera index
            key = (self.sensor_model_data, self.sensor_index)
            self.sensor_info = self.sensor_dimensions.get((key))
            # from IPython import embed; embed()
            # If no direct match, try just with sensor model (for cases without multiple entries)
            if self.sensor_info is None:
                self.sensor_info = next(
                    (
                        value
                        for (model, idx), value in self.sensor_dimensions.items()
                        if model == self.sensor_model_data
                    ),
                    None,
                )
        else:
            # Use default when sensor_model_data is 'default'
            self.sensor_info = self.sensor_dimensions.get(("default", "nan"))

        # Ensure we have valid sensor_info; otherwise, log error or take necessary action
        if not self.sensor_info:
            #            logger.error(

            print(
                f"No sensor information found for {self.file_name} with sensor model {self.sensor_model_data} and rig camera index {self.sensor_index}. Using defaults."
            )
            self.sensor_info = self.sensor_dimensions.get(("default", "nan"))

        self.drone_make = self.sensor_info[0]
        self.drone_model = self.sensor_info[1]
        self.camera_make = self.sensor_info[2]
        self.sensor_model = self.sensor_info[3]
        self.cam_index = self.sensor_info[4]
        self.sensor_width = self.sensor_info[5]
        self.sensor_height = self.sensor_info[6]
        self.lens_FOV_width = self.sensor_info[7]
        self.lens_FOV_height = self.sensor_info[8]

        # Special case
        if self.sensor_model in ["FC2103", "FC220", "FC300X", "FC200"]:
            self.sensor_model = f"{self.drone_model} {self.sensor_model}"

        if self.sensor_model and self.drone_make is None:
            self.drone_model = ""
            self.drone_make = "Unknown Drone"

        self.refresh_derived_properties()
        self.create_hash()

    def set_relative_altitude(self, relative_altitude: float):
        self.relative_altitude = relative_altitude
        self.refresh_derived_properties()

    def refresh_derived_properties(self):
        self.gsd = (self.sensor_width * self.relative_altitude) / (
            self.focal_length * self.image_width
        )
        self.create_properties()

    # def find_declination(altitude, focal_length, drone_latitude, drone_longitude, datetime_original):
    def find_declination(self):
        str_date = datetime.strptime(self.datetime_original, "%Y:%m:%d %H:%M:%S")

        if str(str_date.year) > str(2019):
            mag_date = api.dti.date(str_date.year, str_date.month, str_date.day)
            # Find the magnetic declination reference
            model = api.Model(mag_date.year)
            field_point = model.at(
                lat_dd=self.latitude,
                lon_dd=self.longitude,
                alt_ft=self.relative_altitude,
                date=mag_date,
            )
            declination = field_point.dec
        else:
            calculator = MagneticFieldCalculator()
            model = calculator.calculate(
                latitude=self.latitude, longitude=self.longitude
            )
            dec = model["field-value"]["declination"]
            declination = dec["value"]

        if self.relative_altitude < 0 or self.focal_length <= 0:
            warnings.warn("Altitude and focal length must be positive.")
        self.declination = declination

    def create_geojson_feature(self, properties):
        """
        Create GeoJSON features from image metadata **without geojson or geojson_rewind**.
        Uses shapely + json (standard library).
        """

        # Create polygon
        polygon = Polygon(self.footprint_coordinates)

        # Ensure proper right-hand rule (counter-clockwise winding)
        polygon = orient(polygon, sign=1)

        # GeoJSON polygon
        type_polygon = {
            "type": "Polygon",
            "coordinates": mapping(polygon)["coordinates"],
        }

        # GeoJSON point
        type_point = {"type": "Point", "coordinates": [self.longitude, self.latitude]}

        # Store as feature dicts
        self.feature_point = {
            "type": "Feature",
            "geometry": type_point,
            "properties": properties,
        }

        self.feature_polygon = {
            "type": "Feature",
            "geometry": type_polygon,
            "properties": properties,
        }

    def create_properties(self):
        self.properties = dict(
            File_Name=self.file_name,
            Focal_Length=self.focal_length,
            Image_Width=self.image_width,
            Image_Height=self.image_height,
            Sensor_Model=self.sensor_model,
            Sensor_index=self.sensor_index,
            Sensor_Make=self.sensor_make,
            RelativeAltitude=self.relative_altitude,
            AbsoluteAltitude=self.absolute_altitude,
            FlightYawDegree=self.flight_yaw_degree,
            FlightPitchDegree=self.flight_pitch_degree,
            FlightRollDegree=self.flight_roll_degree,
            DateTimeOriginal=self.datetime_original,
            GimbalPitchDegree=self.gimbal_pitch_degree,
            GimbalYawDegree=self.gimbal_yaw_degree,
            GimbalRollDegree=self.gimbal_roll_degree,
            DroneCoordinates=[self.longitude, self.latitude],
            Sensor_Width=self.sensor_width,
            Sensor_Height=self.sensor_height,
            CameraMake=self.camera_make,
            Drone_Make=self.drone_make,
            Drone_Model=self.drone_model,
            MaxApertureValue=self.max_aperture_value,
            lens_FOV1h=self.lens_FOV_height,
            lens_FOVw1=self.lens_FOV_width,
            GSD=self.gsd,
        )
        if self.gimbal_pitch_degree == 999:
            self.properties["FlightYawDegree"] = self.gimbal_yaw_degree
            self.properties["FlightPitchDegree"] = self.gimbal_pitch_degree
            self.properties["FlightRollDegree"] = self.gimbal_roll_degree

    def create_hash(self) -> bool:
        self.drone_hash = hash(
            (
                self.drone_make,
                self.drone_model,
                self.camera_make,
                self.sensor_model,
                self.sensor_width,
                self.sensor_height,
                self.lens_FOV_width,
                self.lens_FOV_height,
                self.focal_length,
                self.max_aperture_value,
            )
        )
