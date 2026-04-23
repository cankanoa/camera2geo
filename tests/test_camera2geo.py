from camera2geo import apply_metadata, read_metadata, search_cameras, search_lenses


def test_public_metadata_apis_exist():
    assert callable(read_metadata)
    assert callable(apply_metadata)


def test_search_cameras_and_lenses():
    """Ensure that camera + lens lookup returns something at all."""

    found_cams = search_cameras("DJI", "FC", True)
    assert found_cams, "search_cameras() returned nothing"

    found_lenses = search_lenses(found_cams[0], "DJI", "", True)
    assert found_lenses, "search_lenses() returned nothing"
