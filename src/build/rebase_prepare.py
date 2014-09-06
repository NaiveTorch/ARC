#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Prepares the list of commands required to rebase a directory.

import argparse
import os
import sys

_SKIP_FILES = ['config.py']


def _list_files(base_path):
  result = []
  for root, dirs, files in os.walk(base_path):
    root = os.path.relpath(root, base_path)
    for one_file in files:
      if not one_file in _SKIP_FILES:
        result.append(os.path.join(root, one_file))
  return result


def _is_valid_base(base):
  if base.startswith('mods/') or base.startswith('third_party/'):
    return False
  # Require base to actually be the root of a git checkout, otherwise
  # the rebase_src.py commands we print out will fail.
  git_path = os.path.join('third_party', 'android', base, '.git')
  if not os.path.exists(git_path):
    return False
  return True


def _find_dir_containing(android_path, start_file, expected_child):
  """Looks for the deepest dir, which a parent of start_file and
  contains expected_child. Returns empty string if not found."""
  dir_name = os.path.dirname(start_file)
  while dir_name:
    if os.path.exists(os.path.join(android_path, dir_name, expected_child)):
      return dir_name
    dir_name = os.path.dirname(dir_name)
  return ''


def _emit_rebase_cmd(mods_base, mods_file, android_path, android_file):
  # "mods" here means a file and its base (for example frameworks/base) found
  # under "android" directory that needs rebasing. "new" refers to the new
  # position where this file should live after rebase (e.g., frameworks/av).
  new_base = _find_dir_containing(android_path, android_file, '.git')
  new_file = os.path.relpath(android_file, new_base)
  if new_base.startswith('third_party/'):
    new_base = new_base[9:]
  if not new_base:
    print 'Unable to find new base for', android_file
    return
  if new_file != mods_file:
    print '  src/build/rebase_file.py %s %s %s %s' % (new_base, new_file,
                                                      mods_base, mods_file)
  elif new_base == mods_base:
    print '  src/build/rebase_file.py %s %s' % (new_base, new_file)
  else:
    print '  src/build/rebase_file.py %s %s %s' % (new_base, new_file,
                                                   mods_base)


def _rebase_mods_file(mods_file, mods_base, android_files, android_path):
  found = False
  expected_suffix = os.path.sep + os.path.basename(mods_file)
  for android_file in android_files:
    if android_file.endswith(expected_suffix):
      if not found:
        print 'Suggestions for', mods_file
        found = True
      # TODO(igorc): Consider using "diff a b | wc -l" to find
      # the best candidate command line.
      _emit_rebase_cmd(mods_base, mods_file, android_path, android_file)
  if not found:
    print 'No matches for', mods_file


def main():
  parser = argparse.ArgumentParser(description='Propose rebase commands for '
                                   'matching files.')
  parser.add_argument(dest='base', metavar='<base_dir>',
                      help=('Base directory.  Note: has to be one of the '
                            'third_party/ git repos.'))
  parser.add_argument(dest='target', metavar='<target_dir>',
                      help='Target directory.')
  args = parser.parse_args()

  mods_base = args.base
  if not _is_valid_base(mods_base):
    print "Invalid base:", mods_base
    parser.print_help()
    return 1
  mods_files = _list_files(os.path.join('mods', 'android', mods_base))
  mods_files.sort()

  android_files = []
  android_path = args.target
  for path in _list_files(android_path):
    if path.startswith('out/'):
      continue
    android_files.append(path)

  if not mods_files:
    raise Exception('No source files found at src/' + mods_base)
  if not android_files:
    raise Exception('No Android files found at ' + android_path)

  for mods_file in mods_files:
    if 'arc/' in mods_file:
      continue
    _rebase_mods_file(mods_file, mods_base, android_files, android_path)

  print 'Total %d files to rebase' % len(mods_files)

  return 0

if __name__ == '__main__':
  sys.exit(main())
