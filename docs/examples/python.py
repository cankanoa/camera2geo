import os
from camera2geo import *

working_directory = os.getcwd()

# %% Search for cameras
cameras = search_cameras(
    cam_maker = "DJI",
    cam_model = "Mavic Pro"
)

# %% Search lenses
search_lenses(
    cameras[0],
    lens_maker = "DJI",
    lens_model = "Mavic Pro"
)

# %% Read current metadata used in main function, first value in list takes president over subsequent ones

read_metadata(
    input_images=f"{working_directory}/data_mavic2pro/input/*.*"
)

# %% Add image metadata or remove it by setting to None
# DJI_0812.JPG has the FocalLength metadata param removed, here we add it back as a demonstration
apply_metadata(
    input_images=f"{working_directory}/data_mavic2pro/input/DJI_0812.*",
    metadata={
        "EXIF:FocalLength": 10.26, # Correct value: 10.26
    }
)

# %% Camera space to geographic space for mavic 2 pro test images

camera2geo(
    input_images=f"{working_directory}/data_mavic2pro/input/*.*",
    output_images= f"{working_directory}/data_mavic2pro/output/$.tif",
    epsg = 4326,
    correct_magnetic_declination = True,
    cog = True,
    image_equalize = False,
    lens_correction = True,
    elevation_data = True,
)