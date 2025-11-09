import os
from camera2geo import *

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

# %%
# TODO: add function to attach lense metadata to images

# %% Camera space to geographic space for mavic 2 pro test images
working_directory = os.getcwd()

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