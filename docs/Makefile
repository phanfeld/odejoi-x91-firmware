# Build the documentation with the Sphinx of the project's own virtual environment (../.venv-docs).
#   make html     ->  _build/html/index.html
#   make clean
SPHINXBUILD ?= ../.venv-docs/bin/sphinx-build
SOURCEDIR    = .
BUILDDIR     = _build

.PHONY: html clean linkcheck

html:
	$(SPHINXBUILD) -b html -W --keep-going "$(SOURCEDIR)" "$(BUILDDIR)/html"

linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

clean:
	rm -rf "$(BUILDDIR)"
