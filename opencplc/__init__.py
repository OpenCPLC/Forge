# opencplc/__init__.py

"""Forge package metadata; the CLI lives in `__main__`, nothing is re-exported."""

__version__ = "0.6.2"
__repo__ = "OpenCPLC/Forge"
__python__ = ">=3.12"
__description__ = "Project configuration and build tool for OpenCPLC"
__author__ = "Xaeian"
__keywords__ = ["embedded", "stm32", "opencplc", "build", "forge"]
# `serial` for `make update`, `yaml` for `lint.yaml`, 1.2.2 for `JSON.parse` of the key files
__dependencies__ = ["xaeian[serial,yaml]>=1.2.2", "packaging"]
__scripts__ = {
  "opencplc": "opencplc.__main__:main",
}
