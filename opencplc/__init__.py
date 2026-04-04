# opencplc/__init__.py

__version__ = "0.1.3"
__repo__ = "OpenCPLC/Forge"
__python__ = ">=3.12"
__description__ = "Project configuration and build tool for OpenCPLC"
__author__ = "Xaeian"
__keywords__ = ["embedded", "stm32", "opencplc", "build", "forge"]
__dependencies__ = ["xaeian", "packaging"]
__scripts__ = {
  "opencplc": "opencplc.__main__:main",
}
