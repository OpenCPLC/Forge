# opencplc/utils/__init__.py

from .files import (
  files_list, files_mdate, files_mdate_max, last_modification,
  create_file, get_project_list, check_write_permission
)
from .text import (
  line_remove, line_replace, line_add_before, lines_clear,
  swap_comment_lines, get_vars, get_var, find_missing_keys,
  last_line_len
)
from .version import (
  version_real, version_older_than, version_check,
  git_get_refs, git_clone, git_clone_missing
)
from .network import download, unzip, project_remote
from .install import (
  ENV, program_version, install, install_missing_add_path,
  install_toolchains, verify_compiler,
  RESET_CONSOLE, FTP_PATH, INSTALL_PATH
)
from .hash import hash_string, c_code_enum
from .common import (
  to_int, is_yes, color_url, assign_name, detect_os, is_windows, is_linux,
  validate_project_name, detect_shell, is_pwsh
)

__all__ = [
  "files_list", "files_mdate", "files_mdate_max", "last_modification",
  "create_file", "get_project_list", "check_write_permission",
  "line_remove", "line_replace", "line_add_before", "lines_clear",
  "swap_comment_lines", "get_vars", "get_var", "find_missing_keys",
  "last_line_len",
  "version_real", "version_older_than", "version_check",
  "git_get_refs", "git_clone", "git_clone_missing",
  "download", "unzip", "project_remote",
  "ENV", "program_version", "install", "install_missing_add_path",
  "install_toolchains", "verify_compiler",
  "RESET_CONSOLE", "FTP_PATH", "INSTALL_PATH",
  "hash_string", "c_code_enum",
  "to_int", "is_yes", "color_url", "assign_name", "detect_os", "is_windows", "is_linux",
  "validate_project_name", "detect_shell", "is_pwsh"
]
