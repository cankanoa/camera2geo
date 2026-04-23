import yaml

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterDefinition
)
from .camera2geo.main import camera2geo
from .camera2geo.search import search_cameras, search_lenses
from .camera2geo.metadata import apply_metadata, read_metadata

# CAMERA2GEO

class Camera2GeoProcessingAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    CRS = "CRS"
    DECL = "DECL"
    COG = "COG"
    EQUALIZE = "EQUALIZE"
    LENS = "LENS"

    ELEV_MODE = "ELEV_MODE"
    DSM_PATH = "DSM_PATH"

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

        # Elevation Mode (Radio Buttons)
        elev_choices = [
            "Plane (relative altitude)",
            "Online Elevation via Open Elevation",
            "Local Elevation Raster"
        ]
        param_elev = QgsProcessingParameterEnum(
            self.ELEV_MODE,
            "Elevation Source",
            options=elev_choices,
            defaultValue=1,
            allowMultiple=False
        )
        self.addParameter(param_elev)

        # DSM Path (Only visible if Local DSM is selected)
        param_dsm = QgsProcessingParameterFile(
            self.DSM_PATH,
            "Elevation Raster",
            behavior=QgsProcessingParameterFile.File,
            optional=True
        )
        param_dsm.setMetadata({
            "widget_wrapper": {
                "conditional_visibility": {
                    "parameter": self.ELEV_MODE,
                    "value": 2   # visible only when "Local DSM File" selected
                }
            }
        })
        self.addParameter(param_dsm)

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

        elev_mode = self.parameterAsEnum(parameters, self.ELEV_MODE, context)
        dsm_path = self.parameterAsFile(parameters, self.DSM_PATH, context)

        if elev_mode == 0:
            elevation_data = False
        elif elev_mode == 1:
            elevation_data = True
        else:
            elevation_data = dsm_path

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
            elevation_data=elevation_data,
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
