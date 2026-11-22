# opencplc/utils/__init__.py

"""Helpers shared by the CLI modules: palette, files, text, versions, network, tools and probes."""

from .files import (
  load_lines, files_list, last_modification,
  create_file, hidden, get_project_list, project_key, glob_match, ignored, check_write_permission,
  core_version, core_dir, is_core, is_local, project_dir, project_name, home_name,
  full_path, tree_path,
)
from .text import lines_clear, get_vars, define_string, find_missing_keys
from .version import (
  version_real, version_older_than, version_check,
  version_is_release, version_active,
  git_get_refs, git_clone_missing,
)
from .network import download, fetch, project_remote
from .tools import template_paths, ensure_git, ensure_toolchain, ensure_packages, LINT_TOOLS
from .probe import openocd_command, cube_bin, cube_cli, cube_found, CUBE_URL
from .hash import c_code_enum
from .palette import (
  color_file, color_symbol, color_include, color_key, color_key_file,
  color_chip, color_board, color_boot,
  color_config, color_program, color_value, color_choice, color_command, color_image,
  color_folder, color_link,
  color_version, color_wrong, color_passed, color_bad,
)
from .common import is_yes, color_pro_file, color_main_h, assign_name, validate_project_name

__all__ = [
  "load_lines", "files_list", "last_modification",
  "create_file", "hidden", "get_project_list", "project_key", "glob_match", "ignored",
  "check_write_permission",
  "core_version", "core_dir", "is_core", "is_local", "project_dir", "project_name", "home_name",
  "full_path", "tree_path",
  "lines_clear",
  "get_vars", "define_string", "find_missing_keys",
  "version_real", "version_older_than", "version_check",
  "version_is_release", "version_active",
  "git_get_refs", "git_clone_missing",
  "download", "fetch", "project_remote",
  "template_paths", "ensure_git", "ensure_toolchain", "ensure_packages", "LINT_TOOLS",
  "openocd_command", "cube_bin", "cube_cli", "cube_found", "CUBE_URL",
  "c_code_enum",
  "color_file", "color_symbol", "color_include", "color_key", "color_key_file",
  "color_chip", "color_board", "color_boot",
  "color_config", "color_program", "color_value", "color_choice", "color_command", "color_image",
  "color_folder", "color_link",
  "color_version", "color_wrong", "color_passed", "color_bad",
  "is_yes", "color_pro_file", "color_main_h", "assign_name", "validate_project_name",
]
