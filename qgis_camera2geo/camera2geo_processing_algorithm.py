import os
import yaml

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterExtent,
    QgsCoordinateReferenceSystem,
)
from .camera2geo.main import camera2geo
from .camera2geo.search import search_cameras, search_lenses
from .camera2geo.metadata import apply_metadata, read_metadata
from .elevation_surface import get_opentopo_cache_file

# CAMERA2GEO

class Camera2GeoProcessingAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    CRS = "CRS"
    DECL = "DECL"
    COG = "COG"
    EQUALIZE = "EQUALIZE"
    LENS = "LENS"

    PROJECTION = "PROJECTION"
    ELEVATION_SURFACE = "ELEVATION_SURFACE"
    ELEVATION_FILE = "ELEVATION_FILE"
    OPENTOPO_EXTENT = "OPENTOPO_EXTENT"
    OPENTOPO_API_KEY = "OPENTOPO_API_KEY"
    REPROJECT_ELEVATION_POINT = "REPROJECT_ELEVATION_POINT"

    SENSOR_W = "SENSOR_W"
    SENSOR_H = "SENSOR_H"
    NO_DATA_VALUE = "NO_DATA_VALUE"
    REPLACE_NODATA_VALUE = "REPLACE_NODATA_VALUE"


    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterFile(
            self.INPUT,
            "Input Images",
        ))

        self.addParameter(QgsProcessingParameterFile(
            self.OUTPUT,
            "Output Folder (folder or glob)",
            behavior=QgsProcessingParameterFile.Folder
        ))

        # CRS + Basic Options
        self.addParameter(QgsProcessingParameterCrs(
            self.CRS,
            "Output CRS",
            defaultValue="EPSG:4326"
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.DECL,
            "Correct Magnetic Declination",
            defaultValue=False
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.COG,
            "Output as COG",
            defaultValue=False
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.EQUALIZE,
            "Image Equalization",
            defaultValue=False
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.LENS,
            "Lens Distortion Correction",
            defaultValue=False
        ))

        projection_choices = ["Point", "Mesh"]
        param_projection = QgsProcessingParameterEnum(
            self.PROJECTION,
            "Projection",
            options=projection_choices,
            defaultValue=0,
            allowMultiple=False
        )
        self.addParameter(param_projection)

        surface_choices = ["Local File Path", "OpenTopo Extent (SRTMGL1_E)"]
        param_surface = QgsProcessingParameterEnum(
            self.ELEVATION_SURFACE,
            "Elevation Surface",
            options=surface_choices,
            defaultValue=1,
            allowMultiple=False,
        )
        self.addParameter(param_surface)

        param_dsm = QgsProcessingParameterFile(
            self.ELEVATION_FILE,
            "Elevation Raster",
            behavior=QgsProcessingParameterFile.File,
            optional=True
        )
        self.addParameter(param_dsm)

        opentopo_extent = QgsProcessingParameterExtent(
            self.OPENTOPO_EXTENT,
            "OpenTopo Extent (WGS84 bounding box)",
            optional=True,
        )
        self.addParameter(opentopo_extent)

        opentopo_api_key = QgsProcessingParameterString(
            self.OPENTOPO_API_KEY,
            "OpenTopo API Key",
            optional=True,
        )
        self.addParameter(opentopo_api_key)

        reproject_elevation_point = QgsProcessingParameterBoolean(
            self.REPROJECT_ELEVATION_POINT,
            "Reproject point coords into elevation CRS",
            defaultValue=True,
        )
        reproject_elevation_point.setFlags(
            reproject_elevation_point.flags()
            | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(reproject_elevation_point)

        # Advanced: Sensor Dimensions
        sensor_w = QgsProcessingParameterNumber(
            self.SENSOR_W,
            "Sensor Width (mm)",
            type=QgsProcessingParameterNumber.Double,
            optional=True
        )
        sensor_w.setFlags(sensor_w.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(sensor_w)

        sensor_h = QgsProcessingParameterNumber(
            self.SENSOR_H,
            "Sensor Height (mm)",
            type=QgsProcessingParameterNumber.Double,
            optional=True
        )
        sensor_h.setFlags(sensor_h.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(sensor_h)

        no_data_value = QgsProcessingParameterNumber(
            self.NO_DATA_VALUE,
            "Output NoData Value",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0,
            optional=False
        )
        no_data_value.setFlags(
            no_data_value.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(no_data_value)

        replace_nodata_value = QgsProcessingParameterNumber(
            self.REPLACE_NODATA_VALUE,
            "Replace Input Pixels Equal to NoData Value",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1,
            optional=True
        )
        replace_nodata_value.setFlags(
            replace_nodata_value.flags() | QgsProcessingParameterDefinition.FlagAdvanced
        )
        self.addParameter(replace_nodata_value)


    def processAlgorithm(self, parameters, context, feedback):

        projection_index = self.parameterAsEnum(parameters, self.PROJECTION, context)
        elevation_surface_index = self.parameterAsEnum(
            parameters, self.ELEVATION_SURFACE, context
        )
        elevation_file = self.parameterAsFile(parameters, self.ELEVATION_FILE, context)
        projection = {0: "point", 1: "mesh"}[projection_index]
        elevation_surface = {
            0: "local_file",
            1: "opentopo_extent",
        }[elevation_surface_index]
        opentopo_extent_rect = self.parameterAsExtent(
            parameters,
            self.OPENTOPO_EXTENT,
            context,
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        opentopo_extent = None
        if not opentopo_extent_rect.isNull():
            opentopo_extent = (
                opentopo_extent_rect.xMinimum(),
                opentopo_extent_rect.yMinimum(),
                opentopo_extent_rect.xMaximum(),
                opentopo_extent_rect.yMaximum(),
            )
        plugin_dir = os.path.dirname(__file__)

        camera2geo(
            input_images=self.parameterAsString(parameters, self.INPUT, context),
            output_images=self.parameterAsString(parameters, self.OUTPUT, context),
            sensor_width_mm=self.parameterAsDouble(parameters, self.SENSOR_W, context),
            sensor_height_mm=self.parameterAsDouble(parameters, self.SENSOR_H, context),
            epsg=self.parameterAsCrs(parameters, self.CRS, context).postgisSrid(),
            correct_magnetic_declination=self.parameterAsBool(parameters, self.DECL, context),
            cog=self.parameterAsBool(parameters, self.COG, context),
            image_equalize=self.parameterAsBool(parameters, self.EQUALIZE, context),
            lens_correction=self.parameterAsBool(parameters, self.LENS, context),
            projection=projection,
            elevation_surface=elevation_surface,
            elevation_file=elevation_file or None,
            opentopo_extent=opentopo_extent,
            opentopo_api_key=self.parameterAsString(
                parameters, self.OPENTOPO_API_KEY, context
            )
            or None,
            opentopo_cache_file=get_opentopo_cache_file(plugin_dir),
            reproject_elevation_point=self.parameterAsBool(
                parameters, self.REPROJECT_ELEVATION_POINT, context
            ),
            no_data_value=self.parameterAsDouble(parameters, self.NO_DATA_VALUE, context),
            replace_nodata_value=(
                self.parameterAsDouble(parameters, self.REPLACE_NODATA_VALUE, context)
                if self.REPLACE_NODATA_VALUE in parameters
                and parameters[self.REPLACE_NODATA_VALUE] not in (None, "")
                else None
            ),
        )

        return {self.OUTPUT: self.parameterAsString(parameters, self.OUTPUT, context)}
    def name(self): return "camera2geo"
    def displayName(self): return "Camera 2 Geo"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return Camera2GeoProcessingAlgorithm()
    def shortHelpString(self):
        return camera2geo.__doc__ or ""

# CAMERA + LENS SEARCH

class CameraAndLensSearchAlgorithm(QgsProcessingAlgorithm):
    CAM_MAKER = "CAM_MAKER"
    CAM_MODEL = "CAM_MODEL"
    LENS_MAKER = "LENS_MAKER"
    LENS_MODEL = "LENS_MODEL"
    FUZZY = "FUZZY"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.CAM_MAKER, "Camera Maker"))
        self.addParameter(QgsProcessingParameterString(self.CAM_MODEL, "Camera Model"))
        self.addParameter(QgsProcessingParameterString(self.LENS_MAKER, "Lens Maker", optional=True))
        self.addParameter(QgsProcessingParameterString(self.LENS_MODEL, "Lens Model", optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.FUZZY, "Fuzzy Match", defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        cam_maker = self.parameterAsString(parameters, self.CAM_MAKER, context)
        cam_model = self.parameterAsString(parameters, self.CAM_MODEL, context)
        lens_maker = self.parameterAsString(parameters, self.LENS_MAKER, context) or ""
        lens_model = self.parameterAsString(parameters, self.LENS_MODEL, context) or ""
        fuzzy = self.parameterAsBool(parameters, self.FUZZY, context)

        # Always search cameras
        cam = search_cameras(cam_maker, cam_model, fuzzy=fuzzy)
        feedback.pushInfo(f"Camera Match: {cam}")

        # Only search lenses if user entered something for lens fields
        if lens_maker.strip() or lens_model.strip():
            lens = search_lenses(cam[1], lens_maker, lens_model, fuzzy=fuzzy)
            feedback.pushInfo(f"Lens Match: {lens}")
        else:
            feedback.pushInfo("Lens Search not performed")

        return {}

    def name(self): return "camera_lens_search"
    def displayName(self): return "Search Camera and Lens"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return CameraAndLensSearchAlgorithm()
    def shortHelpString(self):
        return (search_cameras.__doc__ + "\n" + search_lenses.__doc__) or ""


# APPLY METADATA

class ApplyMetadataAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    METADATA = "METADATA"
    OUTPUT = "OUTPUT"
    CSV_METADATA_PATH = "CSV_METADATA_PATH"
    CSV_FIELD_TO_HEADER = "CSV_FIELD_TO_HEADER"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.INPUT,
            "Input Images",
        ))

        self.addParameter(QgsProcessingParameterString(
            self.METADATA,
            "Metadata to add as a Python dict with exiv2 tags like tag:value; (e.g. {'Exif.GPSInfo.GPSLatitude':19.95882446})",
            optional=True
        ))

        self.addParameter(QgsProcessingParameterFile(
            self.OUTPUT,
            "Output Folder (folder or glob) or Blank to update Images",
            behavior=QgsProcessingParameterFile.Folder,
            optional=True
        ))

        self.addParameter(QgsProcessingParameterFile(
            self.CSV_METADATA_PATH,
            "CSV Path With Unique Metadata per Image",
            behavior=QgsProcessingParameterFile.File,
            optional=True
        ))

        self.addParameter(QgsProcessingParameterString(
            self.CSV_FIELD_TO_HEADER,
            "Python Dict to Map Unique Metadata: tag:column (must include: {'name':'<col>'} to match)",
            optional=True
        ))

    def processAlgorithm(self, parameters, context, feedback):
        apply_metadata(
            input_images=self.parameterAsString(parameters, self.INPUT, context),
            metadata=(eval(s) if (s := self.parameterAsString(parameters, self.METADATA, context).strip()) else None),
            output_images=self.parameterAsString(parameters, self.OUTPUT, context) or None,
            csv_metadata_path = self.parameterAsString(parameters, self.CSV_METADATA_PATH, context) or None,
            csv_field_to_header = (eval(s) if (s := self.parameterAsString(parameters, self.CSV_FIELD_TO_HEADER, context).strip()) else None),

        )
        return {}

    def name(self): return "apply_metadata"
    def displayName(self): return "Apply Metadata"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return ApplyMetadataAlgorithm()
    def shortHelpString(self):
        return apply_metadata.__doc__ or ""

# READ METADATA

class ReadMetadataAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(self.INPUT, "Input Images (path or glob)"))

    def processAlgorithm(self, parameters, context, feedback):
        result = read_metadata(self.parameterAsFile(parameters, self.INPUT, context))
        feedback.pushInfo(yaml.dump(result, sort_keys=False))
        return {}

    def name(self): return "read_metadata"
    def displayName(self): return "Read Metadata"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return ReadMetadataAlgorithm()
    def shortHelpString(self):
        return read_metadata.__doc__ or ""
