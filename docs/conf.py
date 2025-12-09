# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html


import os
import sys
import importlib.metadata

sys.path.insert(0, os.path.abspath('../src'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'pdfbeaver'
copyright = '2025, qooxzuub'
author = 'qooxzuub'
release = "unknown"

try:
    release = importlib.metadata.version('pdfbeaver')
except importlib.metadata.PackageNotFoundError:
    print("WARNING: pdfbeaver package not found. Is it installed in editable mode?")

version = release
    
# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',      # Reads the docstrings
    'sphinx.ext.napoleon',     # Parses Google/NumPy style
    'sphinx.ext.viewcode',     # Adds links to source code
    'sphinx.ext.intersphinx',  # Links to other libraries (like python docs)
]

# Napoleon settings (optional but good defaults)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
