appname = corptax
package = corptax
version = 1.1.8

# Default goal
.DEFAULT_GOAL := help

# Help
.PHONY: help
help:
	@echo ""
	@echo "$(appname_verbose) Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make [command]"
	@echo ""
	@echo "Commands:"
	@echo "  build               Build the package"
	@echo "  clean               Clean up build artifacts"
	@echo ""

# Build the package
.PHONY: build
build:
	@echo "Building the package"
	@python -m build

# Clean up
#find . -name "*.pyc" -delete
#find . -name "*.pyo" -delete
.PHONY: clean
clean:
	@echo "Cleaning up"
	@rm -rf __pycache__ .pytest_cache .tox .mypy_cache htmlcov dist build *.egg-info
	
# Install
.PHONY: install
install:
	@echo Install ${appname} ${version}
	@echo pip install dist/${appname}-${version}.tar.gz
	@pip install -U dist/${appname}-${version}.tar.gz

