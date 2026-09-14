# opencplc/utils/__init__.py

"""Helpers shared by the CLI modules: files, text, versions, network, tools."""

from .files import (
  load_lines, files_list, files_mdate, files_mdate_max, last_modification,
  create_file, get_project_list, check_write_permission
)
from .text import (
  line_remove, lines_clear,
  get_vars, find_missing_keys, last_line_len
)
from .version import (
  version_real, version_older_than, version_check,
  version_is_release, version_active,
  git_get_refs, git_clone, git_clone_missing
)
from .network import download, fetch, unzip, project_remote
from .tools import tools_dir, template_paths, ensure_git, ensure_tools, verify_compiler
from .hash import hash_string, c_code_enum
from .common import (
  is_yes, color_url, assign_name, validate_project_name
)

__all__ = [
  "load_lines", "files_list", "files_mdate", "files_mdate_max", "last_modification",
  "create_file", "get_project_list", "check_write_permission",
  "line_remove", "lines_clear",
  "get_vars", "find_missing_keys", "last_line_len",
  "version_real", "version_older_than", "version_check",
  "version_is_release", "version_active",
  "git_get_refs", "git_clone", "git_clone_missing",
  "download", "fetch", "unzip", "project_remote",
  "tools_dir", "template_paths", "ensure_git", "ensure_tools", "verify_compiler",
  "hash_string", "c_code_enum",
  "is_yes", "color_url", "assign_name", "validate_project_name",
]
