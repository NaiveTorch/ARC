#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import build_common


_USER = os.getenv('USER', 'default')
_STASH_DIR = os.path.join(tempfile.gettempdir(),
                          'arc-ninja-stash-' + _USER)
_CURRENT_DIR = os.path.join(tempfile.gettempdir(),
                            'arc-ninja-current-' + _USER)


def _copy_off(where):
  if os.path.exists(where):
    shutil.rmtree(where)
  root = build_common.get_arc_root()
  generated_ninja_dir = os.path.join(root, build_common.OUT_DIR,
                                     'generated_ninja')
  top_level_ninja = os.path.join(root, 'build.ninja')
  if (not os.path.exists(top_level_ninja) or
      not os.path.exists(generated_ninja_dir)):
    sys.exit('You must run configure first')

  shutil.copytree(generated_ninja_dir, where)
  shutil.copy(top_level_ninja, where)


def _handle_stash(extra_args=None):
  _copy_off(_STASH_DIR)
  return 0


def _handle_diff_common_setup(extra_args=None):
  if not os.path.exists(_STASH_DIR):
    sys.exit('No stash directory found - run with stash parameter')
  _copy_off(_CURRENT_DIR)


def _handle_diff(extra_args=None, stdout=None):
  if extra_args is None:
    extra_args = []

  _handle_diff_common_setup()
  return subprocess.call(['diff', _STASH_DIR, _CURRENT_DIR] + extra_args,
                         stdout=stdout)


def _handle_meld(extra_args=None):
  with open(os.devnull, 'w') as devnull:
    if _handle_diff(['-q'], stdout=devnull):
      return subprocess.call(['meld', _STASH_DIR, _CURRENT_DIR])
  return 0


def main():
  description = """
Helper script for viewing differences in the ninja build scripts that may be
introduced when changing the ninja-generator scripts."""

  epilog = """
Typical usage:

  1) Save a copy of the current ninja build scripts.

     $ %(prog)s stash

  2) Make changes to the ninja-generator scripts or switch back to the changed
     branch from a previous version.

  3) Check the current scripts against the stashed copy using diff.

     $ %(prog)s diff

If you have meld installed, you can also use it for a nicer interactive diff:

  $ %(prog)s meld"""

  parser = argparse.ArgumentParser(
      description=description,
      epilog=epilog,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('command', choices=['stash', 'diff', 'meld'])
  args, extra_args = parser.parse_known_args()

  return dict(stash=_handle_stash,
              diff=_handle_diff,
              meld=_handle_meld)[args.command](extra_args)

if __name__ == '__main__':
  sys.exit(main())
