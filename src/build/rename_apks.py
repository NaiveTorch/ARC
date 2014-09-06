#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import os
import re
import subprocess
import sys

import toolchain

_AAPT_PATH = toolchain.get_tool('java', 'aapt')


class AnalyzeApk:
  def __init__(self, apk_path):
    self._apk_path = apk_path
    self._package_re = re.compile(r"package: name='([^']*)'.*"
                                  r"versionCode='([^']*)'.*"
                                  r"versionName='([^']*)'")
    self.package_name = None
    self.version_code = None
    self.version_name = None
    self._run_aapt()

  def _run_aapt(self):
    apk_path = self._apk_path
    output = subprocess.check_output([_AAPT_PATH, 'd', 'badging', apk_path])
    m = self._package_re.search(output)
    if not m:
      sys.exit('Cannot find package in aapt output for ' + apk_path)
    self.package_name = m.group(1)
    if m.group(2) == '':
      self.version_code = 0
    else:
      self.version_code = int(m.group(2))
    self.version_name = m.group(3)

  def compute_canonical_name(self, include_version):
    canonical_name = self.package_name
    if include_version:
      canonical_name += '-' + re.sub(r'[^\w\.]+', '_', self.version_name)
      canonical_name += '-%d' % self.version_code
    canonical_name += '.apk'
    return canonical_name


def _update_symlink_dir(opts, apk_info, canonical_versionless_name,
                        canonical_versioned_name_absolute):
  symlink_path = os.path.join(opts.symlink_dir, canonical_versionless_name)
  if os.path.exists(symlink_path):
    if not os.path.islink(symlink_path):
      sys.exit('Path %s is not a symlink' % symlink_path)
    target = os.path.realpath(symlink_path)
    current_version = target[target.rfind('-') + 1:]
    current_version = int(os.path.splitext(current_version)[0])
    print ('Comparing existing version %d from file %s to %d' %
           (current_version,
            canonical_versionless_name, apk_info.version_code))
    if current_version >= apk_info.version_code:
      print 'Not updating symlink'
      return
    print 'Removing symlink ' + symlink_path
    if not opts.dry_run:
      os.unlink(symlink_path)
  print ('Symlinking to %s from %s' %
         (canonical_versioned_name_absolute, symlink_path))
  if not opts.dry_run:
    os.symlink(canonical_versioned_name_absolute, symlink_path)


def _rename(opts):
  for apk in opts.apks:
    apk_info = AnalyzeApk(apk)
    canonical_versioned_name = apk_info.compute_canonical_name(True)
    canonical_versionless_name = apk_info.compute_canonical_name(False)
    dirname = os.path.dirname(apk)
    canonical_versioned_name_absolute = os.path.join(
        dirname, canonical_versioned_name)
    if apk != canonical_versioned_name_absolute:
      print 'Renaming %s to %s' % (apk, canonical_versioned_name_absolute)
      if not opts.dry_run:
        os.rename(apk, canonical_versioned_name_absolute)
    if opts.symlink_dir:
      _update_symlink_dir(opts, apk_info, canonical_versionless_name,
                          canonical_versioned_name_absolute)


def main():
  parser = argparse.ArgumentParser(
      usage=os.path.basename(sys.argv[0]) + ' <options> apks...',
      formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument('--symlink-dir',
                      help='Symlink the bare APK to latest version')
  parser.add_argument('--dry-run', '-n', action='store_true',
                      help='Only print what would be run')
  parser.add_argument('apks', nargs='*', help=argparse.SUPPRESS)

  opts = parser.parse_args(sys.argv[1:])
  if not opts.apks:
    print 'Specify at least one APK file'
    sys.exit(1)
  _rename(opts)


if __name__ == '__main__':
  sys.exit(main())
