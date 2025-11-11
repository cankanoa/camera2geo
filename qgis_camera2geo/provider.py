import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .camera2geo_processing_algorithm import (
    Camera2GeoProcessingAlgorithm,
    CameraAndLensSearchAlgorithm,
    ApplyMetadataAlgorithm,
    ReadMetadataAlgorithm,
)


class Camera2GeoProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(Camera2GeoProcessingAlgorithm())
        self.addAlgorithm(CameraAndLensSearchAlgorithm())
        self.addAlgorithm(ApplyMetadataAlgorithm())
        self.addAlgorithm(ReadMetadataAlgorithm())

    def id(self): return "camera2geo"
    def name(self): return "Camera2Geo"
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon_low.png"))