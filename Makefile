# Python
python-build:
	@echo "Building Python wheel..."
	python -m build --wheel

# QGIS
qgis-build:
	@echo "Creating plugin zip..."
	mkdir -p qgis_camera2geo/src
	cp -r src/* qgis_camera2geo/src/
	PYTHONPATH=. python qgis_camera2geo/build_plugin.py
	find qgis_camera2geo/src -name ".DS_Store" -delete
	find qgis_camera2geo/src -name "__MACOSX" -type d -exec rm -rf {} +
	zip -r qgis_camera2geo.zip qgis_camera2geo/ \
		-x "*.DS_Store" "*__MACOSX*"
	rm -rf qgis_camera2geo/src/
	@echo "Done"

qgis-deploy:
	python spectralmatch_qgis/plugin_upload.py spectralmatch_qgis.zip \
		--username your_username --password your_password