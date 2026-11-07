# opencplc/utils/__init__.py

"""Helpers shared by the CLI modules: files, text, versions, network, tools and probes."""

from .files import (
  load_lines, files_list, last_modification,
  create_file, get_project_list, project_key, ignored, check_write_permission,
  core_version, core_dir, is_core, project_dir, project_name, home_name,
)
from .text import (
  line_remove, lines_clear,
  get_vars, define_string, find_missing_keys,
)
from .version import (
  version_real, version_older_than, version_check,
  version_is_release, version_active,
  git_get_refs, git_clone, git_clone_missing,
)
from .network import download, fetch, unzip, project_remote
from .tools import template_paths, ensure_git, ensure_toolchain
from .probe import openocd_command, cube_bin, cube_cli, cube_found, CUBE_URL
from .hash import hash_string, c_code_enum
from .common import (
  is_yes, color_url, color_command, color_image, color_pro_file, color_main_h,
  assign_name, validate_project_name,
)

__all__ = [
  "load_lines", "files_list", "last_modification",
  "create_file", "get_project_list", "project_key", "ignored", "check_write_permission",
  "core_version", "core_dir", "is_core", "project_dir", "project_name", "home_name",
  "line_remove", "lines_clear",
  "get_vars", "define_string", "find_missing_keys",
  "version_real", "version_older_than", "version_check",
  "version_is_release", "version_active",
  "git_get_refs", "git_clone", "git_clone_missing",
  "download", "fetch", "unzip", "project_remote",
  "template_paths", "ensure_git", "ensure_toolchain",
  "openocd_command", "cube_bin", "cube_cli", "cube_found", "CUBE_URL",
  "hash_string", "c_code_enum",
  "is_yes", "color_url", "color_command", "color_image", "color_pro_file", "color_main_h",
  "assign_name", "validate_project_name",
]
