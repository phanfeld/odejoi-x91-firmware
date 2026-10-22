# Sphinx configuration for the ODEJOI X91 firmware documentation.
# Build: make html (uses ../.venv-docs, see README in this folder).

project = "ODEJOI X91 firmware"
author = "ODEJOI X91 firmware project"
copyright = "2026, ODEJOI X91 firmware project"
release = "stage 24"
version = "24"

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "deflist", "attrs_inline"]
myst_heading_anchors = 3

source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build", "README.md", "requirements.txt"]
language = "en"

html_theme = "sphinx_rtd_theme"
html_title = "ODEJOI X91 firmware"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_show_sourcelink = False
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "prev_next_buttons_location": "both",
}
pygments_style = "sphinx"
