#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Tool to automate rebasing our patched files against upstream
# Android code.

import argparse
import os
import subprocess
import sys

_OLD_TAG_NAME = 'android-4.2_r1'
_NEW_TAG_NAME = 'android-4.4_r1'

_OLD_TMP_FILE = '/tmp/rebase_old_file'
_NEW_TMP_FILE = '/tmp/rebase_new_file'


def _create_dir_for_file(name):
  dir_name = os.path.dirname(name)
  if not os.path.isdir(dir_name):
    os.makedirs(dir_name)


def _save_revision(base, file_name, tag, dst):
  try:
    text = subprocess.check_output(['git', 'show', tag + ':' + file_name],
                                   cwd=base, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError, e:
    if e.output.find('exists on disk, but not in') != -1:
      text = ''
    else:
      raise
  with open(dst, 'w') as f:
    f.write(text)


def _is_valid_base(base):
  if not base.startswith('mods') and not base.startswith('third_party'):
    return base
  raise argparse.ArgumentError(base + ' is not a valid base path')


def _get_tag_hash(tag, repo):
  """Get the equivalent git hash for the given tag in given repository."""
  ref_output = subprocess.check_output(['git', 'show-ref', '-d', tag],
                                       cwd=repo)
  # Expect output of this form:
  # b891ad9ea409911890ceff7200156d74cfd72adc refs/tags/android-4.2_r1
  # f67623632a545bd9ca1d8afefc3dd0789eaba6b3 refs/tags/android-4.2_r1^{}
  # Where the first entry is for the tag's git entry and the second
  # is the interesting one, where it points to.  If the tag itself is
  # a lightweight tag only one line is output and it's the actual
  # hash.  So the first word on the last line is always the interesting
  # one.
  return ref_output.split('\n')[-2].split(' ')[0]


def main():
  progname = os.path.basename(sys.argv[0])
  parser = argparse.ArgumentParser(formatter_class=
                                   argparse.RawTextHelpFormatter, description=
                                   """
The tool will "git mv" the file to the new location and then rebase it.
The corresponding third_party base has to be already updated to the new label.

Examples:
%(progname)s frameworks/base   cmds/bootanimation/BootAnimation.cpp
%(progname)s frameworks/av     media/nuplayer/NuPlayerRenderer.cpp   \
frameworks/base
%(progname)s frameworks/native include/gui/Surface.h                 \
frameworks/base include/surfaceflinger/Surface.h
""" % {"progname": progname})

  parser.add_argument(dest='new_base', metavar='<new_base>',
                      type=_is_valid_base)
  parser.add_argument(dest='new_file', metavar='<new_file>')
  parser.add_argument(dest='old_base', metavar='<old_base>', nargs='?',
                      type=_is_valid_base)
  parser.add_argument(dest='old_file', metavar='<old_file>', nargs='?')
  args = parser.parse_args()

  if not args.old_base:
    args.old_base = args.new_base

  if not args.old_file:
    args.old_file = args.new_file

  old_mods_path = os.path.join('mods', 'android', args.old_base, args.old_file)
  new_mods_path = os.path.join('mods', 'android', args.new_base, args.new_file)
  if not os.path.exists(old_mods_path):
    raise Exception('Old path does not exist: ' + old_mods_path)

  new_third_party_base = os.path.join('third_party', 'android', args.new_base)
  new_tag = subprocess.check_output(['git', 'describe'],
                                    cwd=new_third_party_base)
  if (_get_tag_hash(new_tag.strip(), new_third_party_base) !=
      _get_tag_hash(_NEW_TAG_NAME, new_third_party_base)):
    raise Exception('git checkout at %s is not pointing to %s ' %
                    (new_third_party_base, _NEW_TAG_NAME))

  old_third_party_base = os.path.join('third_party', 'android', args.old_base)
  _save_revision(old_third_party_base, args.old_file, _OLD_TAG_NAME,
                 _OLD_TMP_FILE)
  _save_revision(new_third_party_base, args.new_file, _NEW_TAG_NAME,
                 _NEW_TMP_FILE)

  if new_mods_path != old_mods_path:
    if os.path.exists(new_mods_path):
      raise Exception('New path already exists: ' + new_mods_path)
    _create_dir_for_file(new_mods_path)
    subprocess.check_call(['git', 'mv', old_mods_path, new_mods_path])

  try:
    subprocess.check_call(['merge', new_mods_path, _OLD_TMP_FILE,
                           _NEW_TMP_FILE])
    print 'Merged files automatically, no manual work needed'
  except subprocess.CalledProcessError as e:
    if e.returncode == 1:
      print 'The file needs MERGE:', new_mods_path
    else:
      raise

  return 0

if __name__ == '__main__':
  sys.exit(main())
