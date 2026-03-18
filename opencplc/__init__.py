# opencplc/__init__.py

from .config import VER

__version__ = VER
__repo__ = "OpenCPLC/Forge"
__python__ = ">=3.12"
__description__ = "Project configuration and build tool for OpenCPLC"
__author__ = "Xaeian"
__keywords__ = ["embedded", "stm32", "opencplc", "build", "forge"]
__scripts__ = {
  "opencplc": "opencplc.__main__:main",
}