import lensfunpy
db = lensfunpy.Database()

def search_cameras(
    cam_maker: str,
    cam_model: str,
    fuzzy: bool = True,
    ):
    camera = db.find_cameras(cam_maker, cam_model, fuzzy)[0]
    print(camera)
    return camera

def search_lenses(
    camera,
    lens_maker: str,
    lens_model: str,
    fuzzy: bool = True,
    ):
    lens = db.find_lenses(camera, lens_maker, lens_model, fuzzy)[0]
    print(lens)
    return lens