MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Cleanup
clean:
	rm -rf $(MAKEFILE_DIR)build \
	       $(MAKEFILE_DIR)dist \
	       $(MAKEFILE_DIR)*.egg-info \
	       $(MAKEFILE_DIR)__pycache__ \
	       $(MAKEFILE_DIR).pytest_cache \
		   $(MAKEFILE_DIR)qgis_camera2geo.zip \
		   $(MAKEFILE_DIR)qgis_camera2geo/requirements.txt

# Python
python-build:
	@echo "Building Python wheel..."
	python -m build --wheel

# QGIS
qgis-build:
	@echo "Creating plugin zip..."
	mkdir -p qgis_camera2geo/src
	cp -r src/* qgis_camera2geo/src/
	cp images/icon_low.png qgis_camera2geo/icon_low.png
	PYTHONPATH=. python qgis_camera2geo/build_plugin.py
	find qgis_camera2geo/src -name ".DS_Store" -delete
	find qgis_camera2geo/src -name "__MACOSX" -type d -exec rm -rf {} +
	zip -r qgis_camera2geo.zip qgis_camera2geo/ \
		-x "*.DS_Store" "*__MACOSX*"
	rm -rf qgis_camera2geo/src/
	rm qgis_camera2geo/icon_low.png
	rm qgis_camera2geo/requirements.txt
	@echo "Done"

qgis-deploy:
	python spectralmatch_qgis/plugin_upload.py spectralmatch_qgis.zip \
		--username your_username --password your_password