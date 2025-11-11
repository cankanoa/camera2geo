MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON_LIB := $(MAKEFILE_DIR)camera2geo/

# Cleanup
clean:
	rm -rf $(MAKEFILE_DIR)build \
	       $(MAKEFILE_DIR)dist \
	       $(MAKEFILE_DIR)*.egg-info \
	       $(MAKEFILE_DIR)__pycache__ \
	       $(MAKEFILE_DIR).pytest_cache \
		   $(MAKEFILE_DIR)qgis_camera2geo.zip \
		   $(MAKEFILE_DIR)qgis_camera2geo/requirements.txt

# Python build
python-build:
	@echo "Building Python wheel..."
	python -m build --wheel

# QGIS
qgis-build:
	@echo "Creating plugin zip..."
	mkdir -p qgis_camera2geo/camera2geo
	cp -r camera2geo/* qgis_camera2geo/camera2geo/
	cp images/icon_low.png qgis_camera2geo/icon_low.png
	cp LICENSE qgis_camera2geo/LICENSE
	PYTHONPATH=. python qgis_camera2geo/build_plugin.py

	# Remove caches
	find qgis_camera2geo -name "__pycache__" -type d -exec rm -rf {} +
	find qgis_camera2geo -name "*.pyc" -delete

	zip -r qgis_camera2geo.zip qgis_camera2geo/ \
	  -x "*.DS_Store" "*__MACOSX*"

	rm -rf qgis_camera2geo/camera2geo/
	rm qgis_camera2geo/icon_low.png
	rm qgis_camera2geo/requirements.txt
	rm qgis_camera2geo/LICENSE
	@echo "Done"

qgis-deploy:
	python qgis_camera2geo/plugin_upload.py qgis_camera2geo.zip \
		--username your_username --password your_password

# Versioning
version:
	@if [ -z "$(version)" ]; then \
		echo "Usage: make version version=1.2.3"; \
		exit 1; \
	fi
	@echo "Updating versions to $(version)..."
	sed -i.bak "s/^version = .*/version = \"$(version)\"/" pyproject.toml && rm pyproject.toml.bak
	sed -i.bak "s/^version=.*/version=$(version)/" qgis_camera2geo/metadata.txt && rm qgis_camera2geo/metadata.txt.bak
	git add pyproject.toml qgis_camera2geo/metadata.txt
	git commit -m "Version $(version) released"
	git push origin HEAD
	$(MAKE) tag version=$(version)

tag:
	@if [ -z "$(version)" ]; then \
		echo "Usage: make tag version=1.2.3"; \
		exit 1; \
	fi
	git tag -a v$(version) -m "Version $(version)"
	git push origin v$(version)


# Code formatting
format:
	black $(PYTHON_LIB).

check-format:
	black --check $(PYTHON_LIB).
