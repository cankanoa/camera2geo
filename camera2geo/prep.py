from osgeo import gdal, osr
import csv


def add_relative_altitude_to_csv(
    csv_path: str,
    lat_field: str,
    lon_field: str,
    absolute_field: str,
    output_field: str,
    elevation_raster_path: str,
):
    """
    Compute relative altitude (AGL) for each row in a CSV using a DEM raster. For each record, the function samples the DEM at the latitude/longitude location, computes: relative_altitude = absolute_altitude - dem_elevation and writes the result to `output_field` in the same CSV file.

    Args:
        csv_path (str): Path to the input CSV file.
        lat_field (str): CSV column containing latitude values (WGS84).
        lon_field (str): CSV column containing longitude values (WGS84).
        absolute_field (str): CSV column with absolute altitude (MSL) values.
        output_field (str): Name of the CSV column to write relative AGL values to.
        elevation_raster_path (str): Path to the DEM raster used for elevation sampling.
    """
    # Open DEM
    ds = gdal.Open(elevation_raster_path)
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)

    # DEM CRS
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    dem_crs = srs.CloneGeogCS() if srs.IsProjected() else srs

    # CSV assumed WGS84
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)

    # Coordinate transform
    to_dem = osr.CoordinateTransformation(wgs84, srs)

    # Read all CSV rows
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = rows[0].keys()

    # Add field if missing
    if output_field not in fieldnames:
        fieldnames = list(fieldnames) + [output_field]

    # Process each row
    for r in rows:
        lat = float(r[lat_field])
        lon = float(r[lon_field])
        absolute = float(r[absolute_field])

        # Transform WGS84 → DEM CRS
        x, y, _ = to_dem.TransformPoint(lon, lat)

        # Convert to pixel coordinates
        px = int((x - gt[0]) / gt[1])
        py = int((y - gt[3]) / gt[5])

        try:
            elev = band.ReadAsArray(px, py, 1, 1)[0][0]
        except Exception:
            elev = None

        if elev is None:
            r[output_field] = ""
        else:
            r[output_field] = absolute - float(elev)

    # Write back
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)