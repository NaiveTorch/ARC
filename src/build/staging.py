#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Overlays files from mods over third_party and places them in an output
# staging directory.  This can be used either as a python module or as
# a standalone script.  The latter can be helpful in debugging staging
# or in quickly running staging when you know running all of configure
# is unnecessary.

# Code to create out/staging of properly overlaid files.  All
# files are created as symlinks.

import os
import shutil
import subprocess
import sys

import build_common
import build_options

_GIT_DIR = '.git'
_SRC_DIR = 'src'
_MODS_DIR = 'mods'
_THIRD_PARTY_DIR = 'third_party'
_INTERNAL_MODS_PATH = 'internal/mods'
_INTERNAL_THIRD_PARTY_PATH = 'internal/third_party'

TESTS_BASE_PATH = 'src/build/tests/analyze_diffs'
TESTS_MODS_PATH = os.path.join(TESTS_BASE_PATH, 'mods')
TESTS_THIRD_PARTY_PATH = os.path.join(TESTS_BASE_PATH, 'third_party')


def is_in_staging(input_path):
  """Does this input path look like one that should come from staging.

  Examples are src/*, android/*, libyuv/*, chromium-ppapi/*.
  """
  top_level = input_path.split(os.path.sep)[0]
  return (top_level in ['android', 'src', 'android_libcommon'] or
          os.path.exists(os.path.join('third_party', top_level)))


def get_default_tracking_path(our_path):
  """Returns the tracking path for a given path.

  This is not definitive, and is purely meant to be the default fall-back path
  if the file does not have a FILE_TRACK_TAG explicitly identifying what it is
  based on.

  Returns None if there is no mapping from the input path to a upstream source
  path."""
  tracking_path = None
  if our_path.startswith('mods/'):
    rel_path = os.path.relpath(our_path, 'mods')
    tracking_path = os.path.join('third_party', rel_path)
  elif our_path.startswith(_INTERNAL_MODS_PATH):
    rel_path = os.path.relpath(our_path, _INTERNAL_MODS_PATH)
    tracking_path = os.path.join(_INTERNAL_THIRD_PARTY_PATH, rel_path)
  elif our_path.startswith(TESTS_MODS_PATH):
    rel_path = os.path.relpath(our_path, TESTS_MODS_PATH)
    tracking_path = os.path.join(TESTS_BASE_PATH, 'third_party', rel_path)
  return tracking_path


def get_composite_paths(staging_path):
  if not staging_path.startswith(build_common.get_staging_root()):
    return None, None
  rel_path = os.path.relpath(staging_path, build_common.get_staging_root())
  return (os.path.join('third_party', rel_path),
          os.path.join('mods', rel_path))


def as_staging(input_path, always_stage=False):
  """Convert an input path to a staging path.

  example input:   android/frameworks/base/...
  example staging: STAGING_ROOT/android/frameworks/base/...
  """
  if always_stage or is_in_staging(input_path):
    return os.path.join(build_common.get_staging_root(), input_path)
  else:
    return input_path


def as_real_path(input_path):
  """Convert an input path to a real path.

  example input:   android/frameworks/base/...
  example real path: mods/android/frameworks/base/...
  """
  path = os.path.realpath(as_staging(input_path))
  return os.path.relpath(path, build_common.get_arc_root())


def third_party_to_staging(path):
  """Convert a third party path to a staging path.

  example input:   third_party/android/frameworks/base/...
  example staging: STAGING_ROOT/android/frameworks/base/...

  example input:   internal/third_party/android/frameworks/base/...
  example staging: STAGING_ROOT/android/frameworks/base/...

  When an input path is not in third party directory, the path is returned
  as-is.
  """
  if path.startswith(_THIRD_PARTY_DIR):
    return as_staging(os.path.relpath(path, _THIRD_PARTY_DIR))
  elif path.startswith(_INTERNAL_THIRD_PARTY_PATH):
    return as_staging(os.path.relpath(path, _INTERNAL_THIRD_PARTY_PATH))
  return path


def _create_symlink(src_path, dest_dir):
  """Creates a symlink pointing to src_path in dest_dir with the same name."""
  os.symlink(os.path.relpath(src_path, dest_dir),
             os.path.join(dest_dir, os.path.basename(src_path)))


def _create_overlay_base(base_dir, overlays, dest_dir):
  """Creates symlinks to files and directories in base_dir.

  This is a helper of _create_symlink_tree(). it creates symlinks to files and
  directories in base_dir, except ones in overlays, into dest_dir.
  "overlays" is a list of file and directory basenames in the overlay directory
  corresponding to the given base_dir.
  """
  def relevant(name):
    if base_dir != 'third_party/chromium-ppapi':
      return True
    # Do not create symlinks in out/staging/chromium-ppapi/ except
    # the whitelisted ones below.
    #  - ppapi: We need this to build libchromium_ppapi.a. Note that the files
    #      we need under ppapi/ do not depend on base/.
    #  - breakpad: minidump_generator.cc includes headers in the directory.
    #      Note that chromium_org/ does not have breakpad/.
    #  - third_party: ppapi/generators/ library depeneds on ply library in
    #      third_party directory.
    # Note: Never add 'base' to |whitelist|. Having two base/ directories (one
    #   in out/staging/chromium-ppapi/ and the other in
    #   out/staging/android/external/chromium_org/) makes ARC build fail.
    whitelist = ['ppapi', 'breakpad', 'third_party']
    if name in whitelist:
      return True
    return False

  # If there is no directory at base_dir, it means a new directory is
  # introduced under the corresponding path in mods_root of
  # _create_symlink_tree(). Skip it.
  if not os.path.lexists(base_dir):
    return

  for name in os.listdir(base_dir):
    if not relevant(name):
      continue
    if name == _GIT_DIR or name in overlays:
      continue
    _create_symlink(os.path.join(base_dir, name), dest_dir)


def _create_symlink_tree(mods_root, third_party_root, staging_root):
  """Creates a symlink tree of mods_root overlaid on third_party_root.

  This method creates the symlink tree of mods_root directory (working as
  same as recursive copy, but all files are symlinked instead of actual file
  copy).

  If third_party_root is given, each created directory is overlaid on the
  corresponding directory in third_party_root (if exists).
  For example:
  Suppose mods_root is "mods/", third_party_root is "third_party/" and
  staging_root is "out/staging/", then the symlink tree of mods/android/...
  will be created at out/staging/android/..., with overlaying
  third_party/android/...
  """
  staging_root_parent = os.path.dirname(staging_root)
  build_common.makedirs_safely(staging_root_parent)

  if os.path.exists('mods/chromium-ppapi/base'):
    # See comments in _create_overlay_base.
    raise Exception('Putting headers in mods/chromium-ppapi/base will '
                    'cause code in chromium_org libbase implementation to '
                    'include headers from chromium-ppapi libbase and will '
                    'result in compilation errors or worse.')

  for dirpath, dirs, fnames in os.walk(mods_root):
    # Do not track .git directory.
    if _GIT_DIR in dirs:
      dirs.remove(_GIT_DIR)

    relpath = os.path.relpath(dirpath, mods_root)
    dest_dir = os.path.normpath(os.path.join(staging_root, relpath))
    if not os.path.exists(dest_dir):
      os.mkdir(dest_dir)

    # Create symlinks for files.
    for name in fnames:
      _create_symlink(os.path.join(dirpath, name), dest_dir)

    if third_party_root:
      _create_overlay_base(
          os.path.join(third_party_root, relpath), dirs + fnames, dest_dir)


def _get_link_targets(root):
  link_target_map = {}
  for dirpath, dirs, fnames in os.walk(root):
    for name in fnames:
      link_path = os.path.join(dirpath, name)
      if os.path.islink(link_path):
        link_target_map[link_path] = os.readlink(link_path)
  return link_target_map


def create_staging():
  timer = build_common.SimpleTimer()
  timer.start('Staging source files', True)

  staging_root = build_common.get_staging_root()

  # Store where all the old staging links pointed so we can compare after.
  old_staging_links = _get_link_targets(staging_root)

  if os.path.lexists(staging_root):
    shutil.rmtree(staging_root)

  _create_symlink_tree(_MODS_DIR, _THIRD_PARTY_DIR, staging_root)

  # internal/ is an optional checkout
  if build_options.OPTIONS.internal_apks_source() == 'internal':
    assert build_common.has_internal_checkout()
    for name in os.listdir(_INTERNAL_THIRD_PARTY_PATH):
      if os.path.exists(os.path.join(_THIRD_PARTY_DIR, name)):
        raise Exception('Name conflict between internal/third_party and '
                        'third_party: ' + name)
    _create_symlink_tree(_INTERNAL_MODS_PATH, _INTERNAL_THIRD_PARTY_PATH,
                         staging_root)
    subprocess.check_call('internal/build/fix_staging.py')

  # src/ is not overlaid on any directory.
  _create_symlink_tree(_SRC_DIR, None, os.path.join(staging_root, 'src'))

  # Update modification time for files that do not point to the same location
  # that they pointed to in the previous tree to make sure they are built.
  new_staging_links = _get_link_targets(staging_root)
  for key in new_staging_links:
    if key in old_staging_links:
      if old_staging_links[key] != new_staging_links[key]:
        os.utime(key, None)

  timer.done()
  return True


if __name__ == '__main__':
  sys.exit(not create_staging())
