import os
from camera2geo import *

working_directory = os.getcwd()

# %% Search for cameras
# cameras = search_cameras(
#     cam_maker = "DJI",
#     cam_model = "Mavic Pro"
# )

# %% Search lenses
# search_lenses(
#     cameras[0],
#     lens_maker = "DJI",
#     lens_model = "Mavic Pro"
# )

# %% Prop data

# add_relative_altitude_to_csv(
#     csv_path = "/path/to/metadata/csv/file.csv",
#     lat_field="lat",
#     lon_field="lon",
#     absolute_field="abs_alt",
#     output_field="rel_alt",
#     elevation_raster_path="/elevation/raster/image.tif",
# )

# %% Add image metadata or remove it by setting to None

# Remove metadata fields from DJI_0812.JPG for test
apply_metadata(
    input_images=f"{working_directory}/data_mavic2pro/input/DJI_0812.JPG",
    metadata={
        "Exif.Photo.FocalLength":None,
        "Exif.GPSInfo.GPSLatitude":None,
        "Exif.GPSInfo.GPSLongitude":None,
    },
)

# Add fields back
apply_metadata(
    input_images=f"{working_directory}/data_mavic2pro/input/DJI_0812.JPG",
    metadata={
        # "Exif.GPSInfo.GPSLatitude":None,
        # "Exif.GPSInfo.GPSLongitude":None,
        "Exif.Photo.FocalLength":10.26, # Correct value: 10.26
        # "Exif.Photo.FocalLengthIn35mmFilm":None,
        # "Xmp.drone-dji.RelativeAltitude":None,
        # "Xmp.drone-dji.AbsoluteAltitude":None,
        # "Xmp.drone-dji.GimbalRollDegree":None,
        # "Xmp.drone-dji.GimbalPitchDegree":None,
        # "Xmp.drone-dji.GimbalYawDegree":None,
        # "Xmp.drone-dji.FlightPitchDegree":None,
        # "Xmp.drone-dji.FlightRollDegree":None,
        # "Xmp.drone-dji.FlightYawDegree":None,
        # "Exif.Photo.PixelXDimension":None,
        # "Exif.Photo.PixelYDimension":None,
        # "Exif.Photo.MaxApertureValue":None,
        # "Exif.Photo.DateTimeOriginal":None,
        # "Exif.Image.Model":"Nikon D850",
        # "Xmp.drone-dji.RigCameraIndex":3,
        # "sensor_make":"Nikon",
    },
    csv_metadata_path=f"{working_directory}/data_mavic2pro/input/metadata.csv",
    csv_field_to_header={
        "name":"name",
        "Exif.GPSInfo.GPSLatitude":"lat", # Correct value: 19.5133791944444,
        "Exif.GPSInfo.GPSLongitude":"lon",# Correct value: -154.857850888889
        # "Xmp.drone-dji.AbsoluteAltitude":"abs_alt",
        # "Xmp.drone-dji.RelativeAltitude":"rel_alt",
        # "Xmp.drone-dji.GimbalRollDegree":"omega",
        # "Xmp.drone-dji.GimbalPitchDegree":"phi",
        # "Xmp.drone-dji.GimbalYawDegree":"kappa",
    },
)

# %% Read current metadata used in main function, first value in list takes president over subsequent ones

read_metadata(
    input_images=f"{working_directory}/data_mavic2pro/input/*.JPG"
)

# %% Camera space to geographic space for mavic 2 pro test images

camera2geo(
    input_images=f"{working_directory}/data_mavic2pro/input/*.JPG",
    output_images= f"{working_directory}/data_mavic2pro/output/$.tif",
    epsg = 4326,
    correct_magnetic_declination = False,
    cog = True,
    image_equalize = False,
    lens_correction = True,
    elevation_data = True,
)
