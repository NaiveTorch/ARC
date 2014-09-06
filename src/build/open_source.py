# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Code to query about the open source repository.

import fnmatch
import os

import build_common

METADATA_FILE = 'OPEN_SOURCE'

_cached_is_open_source_repo = None
_cached_is_open_sourced = {}


def is_open_source_repo():
  """Returns whether or not this repository is the open source repository."""
  global _cached_is_open_source_repo
  if _cached_is_open_source_repo is None:
    # The open source metadata is not part of the open source repository.
    _cached_is_open_source_repo = not os.path.exists(METADATA_FILE)
  return _cached_is_open_source_repo


def is_basename_open_sourced(basename, open_source_rules):
  if any([fnmatch.fnmatch(basename, l)
         for l in open_source_rules if not l.startswith('!')]):
    if all([not fnmatch.fnmatch(basename, l[1:])
            for l in open_source_rules if l.startswith('!')]):
      return True
  return False


def _cache_open_sourced(path, result):
  global _cached_is_open_sourced
  _cached_is_open_sourced[path] = result
  return result


# TODO(kmixter): Update to use @functools.lru_cache once we have Python 3.2.
def is_open_sourced(path, skip_directory_contents_check=False):
  """Returns if the given path is open sourced."""
  if is_open_source_repo():
    return True
  if path in ['', '.']:
    return False
  global _cache_open_sourced
  if path in _cached_is_open_sourced:
    return _cached_is_open_sourced[path]
  paths_metadata_file = os.path.join(path, METADATA_FILE)
  if not skip_directory_contents_check and os.path.exists(paths_metadata_file):
    # Check if this is the first call and is a directory.  If so, we consider
    # the whole directory open sourced if either it is listed in the parent
    # (what is checked later) or if it has an OPEN_SOURCE file with only '*' in
    # it.
    rules = build_common.read_metadata_file(paths_metadata_file)
    if len(rules) == 1 and rules[0] == '*':
      return _cache_open_sourced(path, True)
  parent = os.path.dirname(path)
  parent_metadata_file = os.path.join(parent, METADATA_FILE)
  if os.path.exists(parent_metadata_file):
    open_source_rules = build_common.read_metadata_file(parent_metadata_file)
    return _cache_open_sourced(path,
                               is_basename_open_sourced(os.path.basename(path),
                                                        open_source_rules))
  return _cache_open_sourced(
      path,
      is_open_sourced(parent, skip_directory_contents_check=True))
