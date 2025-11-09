import lensfunpy
db = lensfunpy.Database()

def search_cameras(
    cam_maker: str,
    cam_model: str,
    fuzzy: bool = True,
    ):
    """
    Look up cameras by maker and model.

    Args:
        cam_maker: Name of the camera manufacturer.
        cam_model: Name of the camera model.
        fuzzy: If True, allow approximate matching.

    """
    cameras = db.find_cameras(cam_maker, cam_model, fuzzy)
    for c in cameras:
        print(c)
    return cameras

def search_lenses(
    camera,
    lens_maker: str,
    lens_model: str,
    fuzzy: bool = True,
    ):
    """
    Look up lenses compatible with the given camera.

    Args:
        camera: Camera object returned from `search_cameras`.
        lens_maker: Name of the lens manufacturer.
        lens_model: Name of the lens model.
        fuzzy: If True, allow approximate matching.

    """
    lenses = db.find_lenses(camera, lens_maker, lens_model, fuzzy)
    for l in lenses:
        print(l)
    return lenses