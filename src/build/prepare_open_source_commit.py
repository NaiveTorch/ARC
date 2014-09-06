#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import build_common
import logging
import open_source
import os
import shutil
import subprocess
import sys

import util.git


_gitignore_checker = util.git.GitIgnoreChecker()


def _are_files_different(file1, file2):
  s1 = os.stat(file1)
  s2 = os.stat(file2)
  if s1.st_size != s2.st_size:
    return True
  if s1.st_mode != s2.st_mode:
    return True
  with open(os.devnull, 'w') as devnull:
    return subprocess.call(['diff', '-q', file1, file2],
                           stdout=devnull, stderr=devnull) != 0


def _add_and_sync_submodule(dest, force, src_submodule, dest_submodule):
  if dest_submodule is None:
    logging.info('Adding submodule for %s' % src_submodule.path)
    subprocess.check_call(['git', 'submodule', 'add', src_submodule.url,
                           src_submodule.path],
                          cwd=dest)
  if dest_submodule is None or dest_submodule.head != src_submodule.head:
    logging.warning('Updating repository %s' % src_submodule.path)
    if dest_submodule is not None:
      logging.info('Repository was at %s' % dest_submodule.head)
    logging.info('Checking out to %s' % src_submodule.head)
    submodule_path = os.path.join(dest, src_submodule.path)
    subprocess.check_call(['git', 'submodule', 'update', '--init',
                           src_submodule.path],
                          cwd=dest)
    subprocess.check_call(['git', 'remote', 'update'], cwd=submodule_path)
    # Remove any changes to the submodule.  Aborting a checkout or update
    # can result in it appearing that there are local modifications, so
    # this cleans it up.
    if not force and util.git.get_uncommitted_files(cwd=submodule_path):
      logging.error('Uncommitted files in submodule %s, reset or pass --force' %
                    submodule_path)
      sys.exit(1)
    subprocess.check_call(['git', 'reset', '--hard', 'HEAD'],
                          cwd=submodule_path)
    subprocess.check_call(['git', 'checkout', src_submodule.head],
                          cwd=submodule_path)


def _add_and_sync_submodules(dest, force):
  """Make submodules match source and dest directories.

  Existing submodules are updated, new ones are added."""
  logging.info('Synchronizing submodules')
  dest_submodules = util.git.get_submodules(dest, use_gitmodules=False)
  dest_submodules_by_path = {}
  for dest_submodule in dest_submodules:
    dest_submodules_by_path[dest_submodule.path] = dest_submodule
  src_submodules = util.git.get_submodules('.', use_gitmodules=True)
  dest_submodules_paths = set(dest_submodules_by_path.keys())
  src_submodules_paths = set([s.path for s in src_submodules])
  for removed_submodule in dest_submodules_paths - src_submodules_paths:
    # TODO(kmixter): Support automatically removing abandoned submodules.
    logging.warning('Submodule %s in open source needs to be removed' %
                    removed_submodule)
  for submodule in src_submodules:
    _add_and_sync_submodule(dest, force, submodule,
                            dest_submodules_by_path.get(submodule.path))
  return src_submodules_paths


def _is_ignorable(path, cwd=None):
  global _gitignore_checker
  if os.path.basename(path) in ['OPEN_SOURCE', '.gitmodules', '.git']:
    return True
  if path.startswith('.git/'):
    return True
  return _gitignore_checker.matches(path, cwd)


def _add_directory_sync_set(src, rel_src_dir, basenames, filter,
                            open_source_rules, sync_set):
  for basename in basenames:
    rel_path = os.path.normpath(os.path.join(rel_src_dir, basename))
    if _is_ignorable(rel_path, cwd=src):
      # Nothing in gitignores should be in the sync set.
      continue
    if filter(basename, open_source_rules):
      sync_set.add(rel_path)


def _find_sync_set(src, src_submodules_paths):
  # sync_set is a list of relative paths of directories and files that need
  # to be synchronized/copied.
  sync_set = set()
  for src_dir, subdirs, filenames in os.walk(src):
    src_dir = os.path.normpath(src_dir)
    rel_src_dir = os.path.relpath(src_dir, src)
    # Prune all submodules, we assume they will all be open sourced but not
    # by copying files, but checking out the same revision.
    subdirs[:] = [s for s in subdirs
                  if not os.path.join(src_dir, s) in src_submodules_paths]
    # Prune any subdirectory matching gitignores, like out.
    subdirs[:] = [s for s in subdirs
                  if not _is_ignorable(os.path.join(src_dir, s), cwd=src)]
    basenames = subdirs + filenames
    if not open_source.METADATA_FILE in filenames:
      # The default (without a new OPEN_SOURCE metdata file) open sourcing of
      # directory is the status of the open sourcing of its parent directory.
      all_included = src_dir in sync_set
      _add_directory_sync_set(src, rel_src_dir, basenames,
                              lambda x, y: all_included,
                              None, sync_set)
    else:
      new_open_source_rules = build_common.read_metadata_file(
          os.path.join(src_dir, open_source.METADATA_FILE))
      _add_directory_sync_set(src, rel_src_dir, basenames,
                              open_source.is_basename_open_sourced,
                              new_open_source_rules,
                              sync_set)

  return sync_set


def _sync_files(dest, src, sync_set):
  """Copies files in sync_set from src to test."""
  for f in sync_set:
    src_path = os.path.join(src, f)
    target_path = os.path.join(dest, f)
    target_dir = os.path.dirname(target_path)
    if os.path.isdir(src_path):
      continue
    if not os.path.exists(target_dir):
      os.makedirs(target_dir)
    if os.path.exists(target_path):
      # Do not update a file that does not change.  Speeds up
      # incremental builds.
      if not _are_files_different(src_path, target_path):
        continue
      os.unlink(target_path)
    logging.warning('Updating %s' % target_path)
    shutil.copy2(src_path, target_path)


def _purge_non_synced_ignored_files(dest, src, sync_set, submodule_paths):
  """Remove any files in dest that should not be there.

  We allow files that were copied from source, exist in submodules,
  and are included in .gitignore files.  All others we remove, assuming
  that they were once part of the repository and are no longer."""
  for dest_dir, subdirs, filenames in os.walk(dest):
    rel_dest_dir = os.path.relpath(dest_dir, dest)
    pruned_subdirs = []
    for s in subdirs:
      rel_dest_subdir = os.path.normpath(os.path.join(rel_dest_dir, s))
      if _is_ignorable(rel_dest_dir, cwd=src):
        continue
      if rel_dest_subdir in submodule_paths:
        continue
      pruned_subdirs.append(s)
    subdirs[:] = pruned_subdirs
    for f in filenames:
      file_path = os.path.normpath(os.path.join(rel_dest_dir, f))
      if _is_ignorable(file_path, cwd=src):
        continue
      if not file_path in sync_set:
        # avoid painful bugs where we delete the git repository.
        assert not file_path.startswith('.git/')
        logging.warning('Removing untracked file %s' % file_path)
        os.unlink(os.path.join(dest, file_path))


def run(dest, force):
  if (not force and util.git.has_initial_commit(cwd=dest) and
      util.git.get_uncommitted_files(cwd=dest)):
    logging.error('Uncommitted files in %s, reset or pass --force' % dest)
    sys.exit(1)
  logging.info('Synchronizing open source tree at: ' + dest)
  submodule_paths = _add_and_sync_submodules(dest, force)
  sync_set = _find_sync_set('.', submodule_paths)
  _sync_files(dest, '.', sync_set)
  _purge_non_synced_ignored_files(dest, '.', sync_set, submodule_paths)


def main():
  assert not open_source.is_open_source_repo(), ('Cannot be run from open '
                                                 'source repo.')
  parser = argparse.ArgumentParser()
  parser.add_argument('--force', action='store_true',
                      help=('Overwrite any changes in the destination'))
  parser.add_argument('--verbose', '-v', action='store_true',
                      help=('Get verbose output'))
  parser.add_argument('dest')
  args = parser.parse_args(sys.argv[1:])
  if args.verbose:
    logging.getLogger().setLevel(logging.INFO)
  run(args.dest, args.force)
  logging.info('%s successfully updated' % args.dest)
  return 0


if __name__ == '__main__':
  sys.exit(main())
