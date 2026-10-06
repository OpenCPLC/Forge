# opencplc/__init__.py

"""Forge package metadata; the CLI lives in `__main__`, nothing is re-exported."""

__version__ = "0.4.8"
__repo__ = "OpenCPLC/Forge"
__python__ = ">=3.12"
__description__ = "Project configuration and build tool for OpenCPLC"
__author__ = "Xaeian"
__keywords__ = ["embedded", "stm32", "opencplc", "build", "forge"]
__dependencies__ = ["xaeian>=1.0.1", "packaging"]
__scripts__ = {
  "opencplc": "opencplc.__main__:main",
}
