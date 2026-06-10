# -*- coding: utf-8 -*-
"""
/***************************************************************************
 camera2geoDialog
                                 A QGIS plugin
 Camera to geographic space image conversion
 ***************************************************************************/
"""

import os

from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QSettings
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)
from qgis.gui import QgsMapToolExtent

from .camera2geo.utils.opentopo import download_opentopo_dem, parse_extent_4326

from .elevation_surface import (
    deserialize_extent,
    get_opentopo_cache_file,
    serialize_extent,
    WGS84_CRS,
)


REPLACE_NODATA_DISABLED = -99999.0


FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "camera2geo_dialog_base.ui")
)


class camera2geoDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.noDataValueSpin.setMinimum(-1e12)
        self.noDataValueSpin.setMaximum(1e12)
        self.noDataValueSpin.setClearValue(0)
        self.replaceNoDataValueSpin.setMinimum(-1e12)
        self.replaceNoDataValueSpin.setMaximum(1e12)
        self.replaceNoDataValueSpin.setSpecialValueText("Disabled")
        self.replaceNoDataValueSpin.setClearValue(REPLACE_NODATA_DISABLED)
        self.openTopoLayerCombo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.openTopoBookmarkCombo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self._draw_extent_tool = None
        self._previous_map_tool = None
        self._configure_extent_controls()
        self.load_settings()

        self.projectionPointRadio.toggled.connect(self.update_surface_ui)
        self.projectionMeshRadio.toggled.connect(self.update_surface_ui)
        self.surfaceLocalFileRadio.toggled.connect(self.update_surface_ui)
        self.surfaceOpenTopoRadio.toggled.connect(self.update_surface_ui)
        self.openTopoLayerCombo.layerChanged.connect(self._apply_layer_extent)
        self.openTopoBookmarkCombo.currentIndexChanged.connect(
            self._apply_selected_bookmark_extent
        )
        self.canvasExtentButton.clicked.connect(self._set_extent_from_canvas)
        self.drawExtentButton.clicked.connect(self._start_draw_extent)
        self.downloadOpenTopoButton.clicked.connect(self._download_opentopo_surface)
        self.update_surface_ui()
        self._fit_to_contents()

    def _configure_extent_controls(self):
        self.openTopoLayerCombo.setAllowEmptyLayer(True, "")
        self._populate_bookmarks()
        if self.iface is not None:
            canvas = self.iface.mapCanvas()
            self._set_extent_from_rectangle(
                canvas.extent(), canvas.mapSettings().destinationCrs()
            )

    def _populate_bookmarks(self):
        self.openTopoBookmarkCombo.blockSignals(True)
        self.openTopoBookmarkCombo.clear()
        self.openTopoBookmarkCombo.addItem("", None)
        managers = [QgsApplication.bookmarkManager()]
        project_manager = QgsProject.instance().bookmarkManager()
        if project_manager is not None:
            managers.append(project_manager)
        seen = set()
        for manager in managers:
            if manager is None:
                continue
            for bookmark in manager.bookmarks():
                bookmark_id = bookmark.id()
                if bookmark_id in seen:
                    continue
                seen.add(bookmark_id)
                label = bookmark.name()
                if bookmark.group():
                    label = f"{bookmark.group()}/{label}"
                self.openTopoBookmarkCombo.addItem(label, bookmark.extent())
        self.openTopoBookmarkCombo.blockSignals(False)

    def update_surface_ui(self):
        use_local_file = self.surfaceLocalFileRadio.isChecked()
        use_opentopo = self.surfaceOpenTopoRadio.isChecked()

        self.openTopoBoundingBoxGroup.setVisible(use_local_file or use_opentopo)
        self.localElevationFileLabel.setVisible(use_local_file)
        self.localElevationFileWidget.setVisible(use_local_file)

        self.openTopoLinksLabel.setVisible(use_opentopo)
        self.openTopoApiKeyLabel.setVisible(use_opentopo)
        self.openTopoApiKeyEdit.setVisible(use_opentopo)
        self.openTopoBoundsLabel.setVisible(use_opentopo)
        self.openTopoExtentEdit.setVisible(use_opentopo)
        self.layerLabel.setVisible(use_opentopo)
        self.openTopoLayerCombo.setVisible(use_opentopo)
        self.bookmarkLabel.setVisible(use_opentopo)
        self.openTopoBookmarkCombo.setVisible(use_opentopo)
        self.canvasExtentButton.setVisible(use_opentopo)
        self.drawExtentButton.setVisible(use_opentopo)
        self.downloadOpenTopoButton.setVisible(use_opentopo)
        self.reprojectElevationPointCheck.setVisible(use_local_file or use_opentopo)
        self._fit_to_contents()

    def load_settings(self):
        s = QSettings()
        self.sensorWidthSpin.setValue(float(s.value("camera2geo/sensor_width_mm", 0) or 0))
        self.sensorHeightSpin.setValue(float(s.value("camera2geo/sensor_height_mm", 0) or 0))
        self.noDataValueSpin.setValue(float(s.value("camera2geo/no_data_value", 0) or 0))
        replace_nodata_value = s.value("camera2geo/replace_nodata_value", 1)
        if replace_nodata_value in (None, ""):
            self.replaceNoDataValueSpin.setValue(REPLACE_NODATA_DISABLED)
        else:
            self.replaceNoDataValueSpin.setValue(float(replace_nodata_value))

        epsg = int(s.value("camera2geo/epsg", 4326))
        self.crsWidget.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(epsg))
        self.declinationCheck.setChecked(
            s.value("camera2geo/correct_magnetic_declination", False, type=bool)
        )
        self.cogCheck.setChecked(s.value("camera2geo/cog", False, type=bool))
        self.lensCheck.setChecked(s.value("camera2geo/lens_correction", False, type=bool))
        self.reprojectElevationPointCheck.setChecked(
            s.value("camera2geo/reproject_elevation_point", True, type=bool)
        )

        projection = s.value("camera2geo/projection", "point")
        if projection == "mesh":
            self.projectionMeshRadio.setChecked(True)
        else:
            self.projectionPointRadio.setChecked(True)

        elevation_surface = s.value("camera2geo/elevation_surface", "opentopo_extent")
        if elevation_surface == "local_file":
            self.surfaceLocalFileRadio.setChecked(True)
        else:
            self.surfaceOpenTopoRadio.setChecked(True)

        self.localElevationFileWidget.setFilePath(
            s.value("camera2geo/elevation_file", "")
        )
        self.openTopoApiKeyEdit.setText(
            s.value("camera2geo/opentopo_api_key", "", type=str)
        )

        saved_extent = deserialize_extent(
            s.value("camera2geo/opentopo_extent", "", type=str)
        )
        if saved_extent is not None:
            self.openTopoExtentEdit.setText(serialize_extent(saved_extent))

        self.pathFieldName.setText(s.value("camera2geo/path_field_name", "photo"))
        self.outputGroup.setText(s.value("camera2geo/output_group", "photos", type=str))
        self.removePreviousPhotos.setChecked(
            s.value("camera2geo/remove_previous_photos", False, type=bool)
        )

        self.update_surface_ui()

    def save_settings(self):
        s = QSettings()
        s.setValue("camera2geo/sensor_width_mm", self.sensorWidthSpin.value())
        s.setValue("camera2geo/sensor_height_mm", self.sensorHeightSpin.value())
        s.setValue("camera2geo/no_data_value", self.noDataValueSpin.value())

        replace_nodata_value = self.replaceNoDataValueSpin.value()
        s.setValue(
            "camera2geo/replace_nodata_value",
            "" if replace_nodata_value == REPLACE_NODATA_DISABLED else replace_nodata_value,
        )
        s.setValue("camera2geo/epsg", self.crsWidget.crs().postgisSrid())
        s.setValue(
            "camera2geo/correct_magnetic_declination",
            self.declinationCheck.isChecked(),
        )
        s.setValue("camera2geo/cog", self.cogCheck.isChecked())
        s.setValue("camera2geo/lens_correction", self.lensCheck.isChecked())
        s.setValue(
            "camera2geo/reproject_elevation_point",
            self.reprojectElevationPointCheck.isChecked(),
        )

        s.setValue(
            "camera2geo/projection",
            "mesh" if self.projectionMeshRadio.isChecked() else "point",
        )
        s.setValue(
            "camera2geo/elevation_surface",
            "local_file" if self.surfaceLocalFileRadio.isChecked() else "opentopo_extent",
        )
        s.setValue("camera2geo/elevation_file", self.localElevationFileWidget.filePath())
        s.setValue("camera2geo/opentopo_api_key", self.openTopoApiKeyEdit.text().strip())
        s.setValue("camera2geo/opentopo_extent", self.openTopoExtentEdit.text().strip())

        s.setValue("camera2geo/path_field_name", self.pathFieldName.text())
        s.setValue("camera2geo/output_group", self.outputGroup.text())
        s.setValue(
            "camera2geo/remove_previous_photos",
            self.removePreviousPhotos.isChecked(),
        )

    def _apply_layer_extent(self, layer):
        if layer is None:
            return
        self.openTopoBookmarkCombo.blockSignals(True)
        self.openTopoBookmarkCombo.setCurrentIndex(0)
        self.openTopoBookmarkCombo.blockSignals(False)
        self._set_extent_from_rectangle(layer.extent(), layer.crs())

    def _apply_selected_bookmark_extent(self, index: int):
        extent = self.openTopoBookmarkCombo.itemData(index)
        if extent is None:
            return
        self.openTopoLayerCombo.blockSignals(True)
        self.openTopoLayerCombo.setLayer(None)
        self.openTopoLayerCombo.blockSignals(False)
        self._set_extent_from_rectangle(extent, extent.crs())

    def _set_extent_from_canvas(self):
        if self.iface is None:
            return
        self.openTopoLayerCombo.blockSignals(True)
        self.openTopoLayerCombo.setLayer(None)
        self.openTopoLayerCombo.blockSignals(False)
        self.openTopoBookmarkCombo.blockSignals(True)
        self.openTopoBookmarkCombo.setCurrentIndex(0)
        self.openTopoBookmarkCombo.blockSignals(False)
        canvas = self.iface.mapCanvas()
        self._set_extent_from_rectangle(
            canvas.extent(), canvas.mapSettings().destinationCrs()
        )

    def _set_extent_from_rectangle(self, rect, source_crs):
        if rect is None or source_crs is None:
            return
        transformed = rect
        if source_crs != WGS84_CRS:
            transform = QgsCoordinateTransform(
                source_crs,
                WGS84_CRS,
                QgsProject.instance(),
            )
            transformed = transform.transformBoundingBox(rect)
        self.openTopoExtentEdit.setText(serialize_extent(transformed))

    def _start_draw_extent(self):
        if self.iface is None:
            return
        canvas = self.iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()
        self._draw_extent_tool = QgsMapToolExtent(canvas)
        self._draw_extent_tool.extentChanged.connect(self._handle_drawn_extent)
        self.hide()
        canvas.setMapTool(self._draw_extent_tool)

    def _handle_drawn_extent(self, rect):
        if self.iface is None:
            return
        self.openTopoLayerCombo.blockSignals(True)
        self.openTopoLayerCombo.setLayer(None)
        self.openTopoLayerCombo.blockSignals(False)
        self.openTopoBookmarkCombo.blockSignals(True)
        self.openTopoBookmarkCombo.setCurrentIndex(0)
        self.openTopoBookmarkCombo.blockSignals(False)
        canvas = self.iface.mapCanvas()
        self._set_extent_from_rectangle(rect, canvas.mapSettings().destinationCrs())
        if self._previous_map_tool is not None:
            canvas.setMapTool(self._previous_map_tool)
            self._previous_map_tool = None
        if self._draw_extent_tool is not None:
            self._draw_extent_tool.deleteLater()
            self._draw_extent_tool = None
        self.show()
        self.raise_()
        self.activateWindow()
        self._fit_to_contents()

    def _fit_to_contents(self):
        self.layout().activate()
        hint = self.sizeHint()
        self.resize(hint.width(), hint.height())

    def _download_opentopo_surface(self):
        try:
            parse_extent_4326(self.openTopoExtentEdit.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Camera2Geo", str(exc))
            return

        api_key = self.openTopoApiKeyEdit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self,
                "Camera2Geo",
                "An OpenTopography API key is required for OpenTopo Extent.",
            )
            return

        self.downloadOpenTopoButton.setEnabled(False)
        try:
            download_opentopo_dem(
                extent_4326=self.openTopoExtentEdit.text().strip(),
                api_key=api_key,
                output_path=get_opentopo_cache_file(os.path.dirname(__file__)),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Camera2Geo", str(exc))
            self.downloadOpenTopoButton.setEnabled(True)
            return

        self.downloadOpenTopoButton.setEnabled(True)
        QMessageBox.information(
            self,
            "Camera2Geo",
            "OpenTopo elevation surface downloaded.",
        )
