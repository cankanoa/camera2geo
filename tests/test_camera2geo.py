import pytest
from pathlib import Path
from PIL import Image
import exiftool

from camera2geo import *


@pytest.fixture(scope="session")
def test_image(tmp_path_factory):
    """Create a tiny test image with realistic EXIF/XMP metadata."""
    tmp_dir = tmp_path_factory.mktemp("data")
    img_path = tmp_dir / "tiny.jpg"

    # Create 1x1 image
    img = Image.new("RGB", (1, 1), (255, 255, 255))
    img.save(img_path)

    with exiftool.ExifToolHelper() as et:
        et.set_tags(
            [str(img_path)],
            {
                # Position
                "EXIF:GPSLatitude": 19.5134089444444,
                "EXIF:GPSLongitude": -154.857994916667,

                # Focal length fields
                "EXIF:FocalLength": 10.26,
                "EXIF:FocalLengthIn35mmFormat": 28,

                # Altitude
                "XMP:RelativeAltitude": "+74.90",
                "XMP:AbsoluteAltitude": "+181.95",

                # Gimbal orientation
                "XMP:GimbalRollDegree": 0.00,
                "XMP:GimbalPitchDegree": -89.9,
                "XMP:GimbalYawDegree": -86.1,

                # Flight orientation
                "XMP:FlightPitchDegree": -2.3,
                "XMP:FlightRollDegree": -4.3,
                "XMP:FlightYawDegree": -77.8,

                # Image size
                "EXIF:ImageWidth": 5472,
                "EXIF:ImageHeight": 3648,

                # Other camera info
                "EXIF:MaxApertureValue": 2.80014,
                "EXIF:DateTimeOriginal": "2025:10:10 13:53:58",
                "EXIF:Model": "L1D-20c",
                "EXIF:Make": "Hasselblad",
            },
            params=["-overwrite_original_in_place"]
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
    # (set in test_image fixture: EXIF:FocalLength = 10.26)
    value = focal.get("EXIF:FocalLength")
    assert value == 10.26, f"Expected focal length 10.26, got {value}"


def test_apply_metadata_update_and_verify(test_image, tmp_path):
    """Change focal length, then re-read metadata to confirm update."""
    new_focal = 12.5

    # Apply in-place
    apply_metadata(
        input_images=str(test_image),
        metadata={"EXIF:FocalLength": new_focal},
        output_images=None,
    )

    # Re-read metadata
    md = read_metadata(str(test_image))
    entry = md[str(test_image)]
    focal = entry["focal_length"]

    value = focal.get("EXIF:FocalLength")
    assert value == new_focal, f"Expected focal length {new_focal}, got {value}"