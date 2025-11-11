import yaml

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMultipleLayers,
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


    def initAlgorithm(self, config=None):

        # Input / Output
        self.addParameter(QgsProcessingParameterFile(
            self.INPUT,
            "Input Images (path or glob)",
            behavior=QgsProcessingParameterFile.File
        ))

        self.addParameter(QgsProcessingParameterFile(
            self.OUTPUT,
            "Output Folder (path or glob)",
            behavior=QgsProcessingParameterFile.File
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
            "Plane (no elevation)",
            "Online Elevation via Open Elevation",
            "Local Elevation Raster"
        ]
        param_elev = QgsProcessingParameterEnum(
            self.ELEV_MODE,
            "Elevation Source",
            options=elev_choices,
            defaultValue=0,  # Plane
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
            input_images=self.parameterAsFile(parameters, self.INPUT, context),
            output_images=self.parameterAsString(parameters, self.OUTPUT, context),
            sensor_width_mm=self.parameterAsDouble(parameters, self.SENSOR_W, context),
            sensor_height_mm=self.parameterAsDouble(parameters, self.SENSOR_H, context),
            epsg=self.parameterAsCrs(parameters, self.CRS, context).postgisSrid(),
            correct_magnetic_declination=self.parameterAsBool(parameters, self.DECL, context),
            cog=self.parameterAsBool(parameters, self.COG, context),
            image_equalize=self.parameterAsBool(parameters, self.EQUALIZE, context),
            lens_correction=self.parameterAsBool(parameters, self.LENS, context),
            elevation_data=elevation_data,
        )

        return {self.OUTPUT: self.parameterAsString(parameters, self.OUTPUT, context)}
    def name(self): return "camera2geo"
    def displayName(self): return "Camera 2 Geo"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return Camera2GeoProcessingAlgorithm()


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


# APPLY METADATA

class ApplyMetadataAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    METADATA = "METADATA"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(self.INPUT, "Input Images (path or glob)", behavior=QgsProcessingParameterFile.File))
        self.addParameter(QgsProcessingParameterString(self.METADATA, "Python Dictionary of Key:Value pairs"))
        self.addParameter(QgsProcessingParameterFile(self.OUTPUT, "Output Images (path or glob) or Blank to Update Images", behavior=QgsProcessingParameterFile.File, optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        apply_metadata(
            input_images=self.parameterAsFile(parameters, self.INPUT, context),
            metadata=eval(self.parameterAsString(parameters, self.METADATA, context)),
            output_images=self.parameterAsString(parameters, self.OUTPUT, context) or None
        )
        return {}

    def name(self): return "apply_metadata"
    def displayName(self): return "Apply Metadata"
    def group(self): return ""
    def groupId(self): return ""
    def createInstance(self): return ApplyMetadataAlgorithm()


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