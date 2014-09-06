#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Adds or updates (and pins) third_party/android directories.

import argparse
import os
import subprocess
import sys

_DEFAULT_BRANCH_NAME = 'android-4.4_r1'


def main():

  parser = argparse.ArgumentParser(usage="""
  <command> [options] <android_dir> [<git_dir>]

Commands:

  add [options] <android_dir> <git_dir>
      Add third_party directory mapped to the given git directory.
      Pins to default branch unless --branch is specified.
      Examples:
        src/build/add_third_party.py add external/bison platform/external/bison
        src/build/add_third_party.py add devices/generic/goldfish \\
          devices/generic/goldfish

  update [options] <android_dir>
      Updates an third_party directory from remote git.
      Pins to default branch unless --branch is specified.
      Example:
        src/build/add_third_party.py update external/bison

  remove <android_dir>
      Removes the submodule and its configuration.
      Does not remove corresponding directory with files.
      Example:
        src/build/add_third_party.py remove external/bison
""", formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument('command', help=argparse.SUPPRESS)
  parser.add_argument('android_dir', help=argparse.SUPPRESS)
  parser.add_argument('git_dir', nargs='?', help=argparse.SUPPRESS)
  parser.add_argument('--branch', metavar='<branch>',
                      default=_DEFAULT_BRANCH_NAME, help='If specified, pin '
                      'submodule to provided branch name.  By default the '
                      'directory is pinned to "%s"' % (_DEFAULT_BRANCH_NAME))
  args = parser.parse_args()

  mode = args.command.lower()
  args.android_dir = args.android_dir

  # error checking
  if mode not in ('add', 'update', 'remove'):
    print "Invalid command: %s" % mode
    parser.print_help()
    return 1

  if (mode == 'add' and not args.git_dir) or (mode != 'add' and args.git_dir):
    print "Invalid number of arguments."
    parser.print_help()
    return 1

  if not args.android_dir.startswith(os.path.join('third_party', 'android')):
    args.android_dir = os.path.join('third_party', 'android', args.android_dir)

  if args.android_dir.endswith(os.path.sep):
    args.android_dir = os.path.dirname(args.android_dir)

  if mode == 'add':
    git_dir_name = args.git_dir
    remote_path = 'https://android.googlesource.com/' + git_dir_name
    subprocess.check_call(
        ['git', 'submodule', 'add', remote_path, args.android_dir])

  if mode in ('add', 'update'):
    subprocess.check_call(['git', 'remote', 'update'], cwd=args.android_dir)
    subprocess.check_call(['git', 'checkout', args.branch],
                          cwd=args.android_dir)
    subprocess.check_call(['git', 'add', args.android_dir])
    subprocess.check_call(['git', 'submodule', 'status', args.android_dir])
  elif mode == 'remove':
    subprocess.check_call(
        ['git', 'config', '-f', '.git/config',
         '--remove-section', 'submodule.' + args.android_dir])
    subprocess.check_call(
        ['git', 'config', '-f', '.gitmodules',
         '--remove-section', 'submodule.' + args.android_dir])
    subprocess.check_call(['git', 'rm', '--cached', args.android_dir])

  return 0

if __name__ == '__main__':
  sys.exit(main())
