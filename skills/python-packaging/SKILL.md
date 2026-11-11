---
name: python-packaging
description: "Package a Python project: pyproject.toml, console-script entry points so it installs as a command, and publishing to PyPI."
---

# Python Packaging

Package a Python project: pyproject.toml, console-script entry points so it installs as a command, and publishing to PyPI.

## pyproject

build-system, project metadata, dependencies.

## CLI

[project.scripts] name = 'pkg.cli:main' so pip install gives a command.

## Publish

python -m build, twine upload, or trusted publishing from GitHub Actions.
