# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Finds and loads config.py files scattered through the source code tree."""

import imp
import os
import os.path
import sys

from build_common import get_arc_root


# List of all modules loaded by this module.
_config_modules = []


def find_name(attribute_name):
  """Iterates over all loaded config modules and does a name lookup on them."""
  for module in _config_modules:
    if hasattr(module, attribute_name):
      yield getattr(module, attribute_name)


def find_config_modules(attribute_name):
  """Finds the loaded config modules that have the specified attribute name."""
  for module in _config_modules:
    if hasattr(module, attribute_name):
      yield module


def _all_config_files(base_paths):
  for base_path in base_paths:
    for root, dirs, files in os.walk(base_path, followlinks=True):
      for name in files:
        if name == 'config.py':
          yield os.path.join(root, name), base_path


def _register_module(module_path, module):
  sys.modules[module_path] = module
  if '.' in module_path:
    parent_name, child_name = module_path.rsplit('.', 1)
    setattr(sys.modules[parent_name], child_name, module)


def _walk_module_path(module_path):
  path = module_path.split('.')
  for index in xrange(len(path) - 1):
    yield '.'.join(path[:index + 1])


def _ensure_parents_exist(module_path):
  for parent in _walk_module_path(module_path):
    if parent not in sys.modules:
      _register_module(parent, imp.new_module(parent))


def load_from(base_paths):
  """Loads all the config.py files found under the base_path.

  The files are loaded as an appropriately named submodule.
  If this function finds base_path/foo/bar/config.py, a module named
  foo.bar is created with its contents, and can be subsequently
  referenced with an 'import foo.bar' (foo.bar.config seemed redundant).
  No __init__.py files are needed.

  Returns a list of all the modules loaded so that later code can optionally do
  some introspection to decide what to do with them.
  """

  # Get the list and sort it to avoid nondeterministic import issues caused by
  # some modules being set up before others.
  all_config_files = sorted(_all_config_files(base_paths))

  # For safety, acquire the import lock.
  imp.acquire_lock()
  try:
    for path_name, base_path in all_config_files:
      # Convert the filename into a dotted python module name.
      # base_path/foo/bar/config.py -> foo.bar
      top_level_dir = os.path.basename(base_path)
      dirs = [top_level_dir]
      relative_path_to_config = os.path.dirname(
          os.path.relpath(path_name, base_path))
      if relative_path_to_config:
        dirs.extend(relative_path_to_config.split(os.sep))
      module_name = '.'.join(dirs)

      # Ensure parent modules exist, creating them if needed.
      _ensure_parents_exist(module_name)

      # Compile and load the source file as a module
      with open(path_name, 'r') as config_file:
        config_module = imp.load_source(module_name, path_name, config_file)

      # Register the module so we can just a later normal looking import to
      # reference it.
      _register_module(module_name, config_module)

      _config_modules.append(config_module)
  finally:
    imp.release_lock()

  return _config_modules


# On the first import, automatically discover all config modules in the project
# for later use, including allowing them to be imported by their containing
# directory name.
paths = [
    os.path.join(get_arc_root(), 'mods', 'android'),
    os.path.join(get_arc_root(), 'mods', 'chromium-ppapi'),
    os.path.join(get_arc_root(), 'mods', 'examples'),
    os.path.join(get_arc_root(), 'mods', 'graphics_translation'),
    os.path.join(get_arc_root(), 'src'),
    os.path.join(get_arc_root(), 'third_party', 'examples'),
]

internal = os.path.join(get_arc_root(), 'internal', 'mods')
if os.path.isdir(internal):
  paths.append(internal)

load_from(paths)
