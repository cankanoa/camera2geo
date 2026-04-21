import pytest
from pathlib import Path
from PIL import Image

pytest.importorskip("exiv2")

from camera2geo import *


@pytest.fixture(scope="session")
def test_image(tmp_path_factory):
    """Create a tiny test image with realistic EXIF/XMP metadata."""
    tmp_dir = tmp_path_factory.mktemp("data")
    img_path = tmp_dir / "tiny.jpg"

    # Create 1x1 image
    img = Image.new("RGB", (1, 1), (255, 255, 255))
    img.save(img_path)

    apply_metadata(
        input_images=str(img_path),
        metadata={
            "Exif.GPSInfo.GPSLatitude": 19.5134089444444,
            "Exif.GPSInfo.GPSLongitude": -154.857994916667,
            "Exif.Photo.FocalLength": 10.26,
            "Exif.Photo.FocalLengthIn35mmFilm": 28,
            "Xmp.drone-dji.RelativeAltitude": "+74.90",
            "Xmp.drone-dji.AbsoluteAltitude": "+181.95",
            "Xmp.drone-dji.GimbalRollDegree": 0.00,
            "Xmp.drone-dji.GimbalPitchDegree": -89.9,
            "Xmp.drone-dji.GimbalYawDegree": -86.1,
            "Xmp.drone-dji.FlightPitchDegree": -2.3,
            "Xmp.drone-dji.FlightRollDegree": -4.3,
            "Xmp.drone-dji.FlightYawDegree": -77.8,
            "Exif.Photo.PixelXDimension": 5472,
            "Exif.Photo.PixelYDimension": 3648,
            "Exif.Photo.MaxApertureValue": 2.80014,
            "Exif.Photo.DateTimeOriginal": "2025:10:10 13:53:58",
            "Exif.Image.Model": "L1D-20c",
            "Exif.Image.Make": "Hasselblad",
        },
    )

    return img_path


@pytest.mark.parametrize("correct_magnetic_declination", [True, False])
@pytest.mark.parametrize("lens_correction", [True, False])
@pytest.mark.parametrize("image_equalize", [True, False])
@pytest.mark.parametrize("elevation_data", [True, False])
def test_camera2geo_param_sweep(
    test_image,
    tmp_path,
    correct_magnetic_declination,
    lens_correction,
    image_equalize,
    elevation_data,
):
    """Run camera2geo over a grid of parameter combinations."""
    output_template = str(tmp_path / "$_Geo.tif")

    outputs = camera2geo(
        input_images=str(test_image),
        output_images=output_template,
        correct_magnetic_declination=correct_magnetic_declination,
        lens_correction=lens_correction,
        image_equalize=image_equalize,
        elevation_data=elevation_data,
    )

    assert len(outputs) == 1
    produced = Path(outputs[0])
    assert produced.exists(), f"Expected output GeoTIFF missing: {produced}"


def test_search_cameras_and_lenses():
    """Ensure that camera + lens lookup returns something at all."""

    found_cams = search_cameras("DJI", "FC", True)
    assert found_cams, "search_cameras() returned nothing"

    found_lenses = search_lenses(found_cams[0], "DJI", "", True)
    assert found_lenses, "search_lenses() returned nothing"


def test_read_metadata_focal_length(test_image):
    """Ensure that read_metadata returns correct focal length."""
    md = read_metadata(str(test_image))

    # Extract result for our single image
    entry = md[str(test_image)]
    focal = entry["focal_length"]

    # The first non-null value should match the test fixture value
    # (set in test_image fixture: Exif.Photo.FocalLength = 10.26)
    value = focal.get("Exif.Photo.FocalLength")
    assert value == 10.26, f"Expected focal length 10.26, got {value}"


def test_apply_metadata_update_and_verify(test_image, tmp_path):
    """Change focal length, then re-read metadata to confirm update."""
    new_focal = 12.5

    # Apply in-place
    apply_metadata(
        input_images=str(test_image),
        metadata={"Exif.Photo.FocalLength": new_focal},
        output_images=None,
    )

    # Re-read metadata
    md = read_metadata(str(test_image))
    entry = md[str(test_image)]
    focal = entry["focal_length"]

    value = focal.get("Exif.Photo.FocalLength")
    assert value == new_focal, f"Expected focal length {new_focal}, got {value}"
