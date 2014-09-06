#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Script to download and build 'adb' command, that's needed to run integration
# tests on Linux, Chrome OS, Windows, and Mac.
#
# For Windows and Mac, this script simply downloads a zip file of Android
# Developer Tools and extracts the pre-built 'adb' executable from the zip
# file.
#
# Usage:
#
# % python src/build/sync_adb.py --target=win-x86_64
# % python src/build/sync_adb.py --target=mac-x86_64
#
# For Linux and Chrome OS, this script downloads a subset of Gingerbread
# source code and builds the 'adb' executable for linux-x86-64 and
# linux-arm. Note that linux-i686 is unnecessary as ARC does not support
# linux-i686-based Chrome OS at this moment. Usage:
#
# Usage:
#
# % python src/build/sync_adb.py --target=linux-arm
# % python src/build/sync_adb.py --target=linux-x86_64
#
# Why building from Gingerbread source code?
#
# Because it's difficult to build 'adb' from the code in third_party/android
# (it's KitKat as of writing), whereas the Gingerbread version is much easier
# to build, and has enough features to use in integration tests.
#
# FWIW, here's why building the 'adb' and its dependencies from
# third_party/android is hard:
#
# 1) It's hard to do so with make_to_ninja.py and ninja_generator.py.
#
# The 'adb' executable of linux-arm is necessary to run integration tests on
# ARM-based Chrome OS devices for bare_metal_arm. To build 'adb' of linux-arm
# as part of the bare_metal_arm build, lots of changes are required to
# make_to_ninja.py and ninja_generator.py that will add siginificant complexity.
#
# 2) It's also hard to do so without make_to_ninja.py and ninja_generator.py.
#
# This is mostly because the newer version of 'adb' depends on openssl which
# is hard to build with a hand-written makefile.
#

import argparse
import cStringIO
import contextlib
import os
import shutil
import stat
import subprocess
import sys
import urllib2
import urlparse
import zipfile

from build_common import SimpleTimer
from build_common import StampFile

ADB_OUTPUT_DIR = 'out/adb'

BRANCH = 'gingerbread-release'
SYSTEM_CORE_URL = 'https://android.googlesource.com/platform/system/core'
ZLIB_URL = 'https://android.googlesource.com/platform/external/zlib'
MAKEFILE = 'src/build/sync_adb.mk'
ADB_SOURCE_VERSION = BRANCH  # Use BRANCH as version.

DEVTOOLS_URLS = {
    'win-x86_64':
    'https://dl.google.com/android/adt/adt-bundle-windows-x86_64-20131030.zip',
    'mac-x86_64':
    'https://dl.google.com/android/adt/adt-bundle-mac-x86_64-20131030.zip',
}


GCC_NAMES = {
    'linux-arm': 'arm-linux-gnueabihf-gcc',
    'linux-x86_64': 'gcc',
}


def _run_git_clone(branch, url, output_dir):
  """Runs git clone per the given branch name, URL and output directory."""
  subprocess.check_call(['git', 'clone', '-b', branch, url, output_dir],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _download_adb_source(force):
  """Downloads the adb source code with git, if needed.

  The source tree will be placed at out/adb/src.
  """
  source_dir = os.path.join(ADB_OUTPUT_DIR, 'src')
  stamp_file_path = os.path.join(source_dir, 'STAMP')
  stamp_file = StampFile(ADB_SOURCE_VERSION, stamp_file_path,
                         force=force)
  if stamp_file.is_up_to_date():
    return

  if os.path.exists(source_dir):
    shutil.rmtree(source_dir)

  try:
    timer = SimpleTimer()
    timer.start('Downloading the adb source code', show=True)
    _run_git_clone(BRANCH, SYSTEM_CORE_URL,
                   os.path.join(ADB_OUTPUT_DIR, 'src/system/core'))
    _run_git_clone(BRANCH, ZLIB_URL,
                   os.path.join(ADB_OUTPUT_DIR, 'src/external/zlib'))
    timer.done()
  except Exception as exception:
    print exception
    raise Exception('Failed to download the adb source code')

  stamp_file.update()


def _build_adb(target, force):
  """Builds the adb executable, if needed.

  The resulting executable will be placed at out/adb/<target>/adb.
  """

  build_dir = os.path.join(ADB_OUTPUT_DIR, target)
  stamp_file_path = os.path.join(build_dir, 'STAMP')
  stamp_file = StampFile(ADB_SOURCE_VERSION, stamp_file_path,
                         force=force)
  if stamp_file.is_up_to_date():
    return

  gcc = GCC_NAMES[target]
  try:
    timer = SimpleTimer()
    timer.start('Building the adb executable for %s' % target, show=True)
    subprocess.check_call(
        ['make', '-j16', '-f', MAKEFILE, 'CC=' + gcc, 'TARGET=' + target],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timer.done()
  except Exception as exception:
    print exception
    raise Exception('Failed to build the adb executable')

  stamp_file.update()


def _download_adb(target, force):
  """Downloads the adb executable for Windows or Mac, if needed.

  The downloaded executable will be placed at out/adb/win-x86_64/adb.exe or
  out/adb/mac-x86_64/adb.
  """

  # URL looks like 'https://dl.google.com/android/adt/adt-xxx.zip'
  url = DEVTOOLS_URLS[target]

  output_dir = os.path.join(ADB_OUTPUT_DIR, target)
  stamp_file_path = os.path.join(output_dir, 'STAMP')
  stamp_file = StampFile(url,  # Use URL as the version.
                         stamp_file_path, force=force)
  if stamp_file.is_up_to_date():
    return

  if os.path.exists(output_dir):
    shutil.rmtree(output_dir)
  os.makedirs(output_dir)

  is_windows = target.startswith('win-')
  adb_base_name = 'adb.exe' if is_windows else 'adb'
  # The output file name looks like 'out/adb/win-x86_64/adb.exe'
  adb_output_file_name = os.path.join(output_dir, adb_base_name)

  zip_file_name = os.path.basename(urlparse.urlparse(url).path)
  zip_name = os.path.splitext(zip_file_name)[0]
  # The adb path in zip looks like 'adt-xxx/sdk/platform-tools/adb.exe'
  adb_path_in_zip = os.path.join(zip_name, 'sdk/platform-tools', adb_base_name)
  # For Windows, AdbWinApi.dll is also needed.
  if is_windows:
    dll_path_in_zip = os.path.join(zip_name, 'sdk/platform-tools/AdbWinApi.dll')
    dll_output_file_name = os.path.join(output_dir, 'AdbWinApi.dll')

  try:
    timer = SimpleTimer()
    timer.start('Downloading the adb executable for %s' % target, show=True)
    with contextlib.closing(urllib2.urlopen(url)) as stream, (
        zipfile.ZipFile(cStringIO.StringIO(stream.read()))) as zip_archive:
      with open(adb_output_file_name, 'w') as adb_file:
        # Don't use zipfile.extract() as it creates sub directories.
        content = zip_archive.read(adb_path_in_zip)
        adb_file.write(content)
      os.chmod(adb_output_file_name, stat.S_IRWXU)
      # Also extract AdbWinApi.dll for Windows.
      if is_windows:
        with open(dll_output_file_name, 'w') as dll_file:
          content = zip_archive.read(dll_path_in_zip)
          dll_file.write(content)
        os.chmod(dll_output_file_name, stat.S_IRWXU)
    timer.done()
  except Exception as exception:
    print exception
    raise Exception('Failed to download the adb executable')

  stamp_file.update()


def run(target, force=False):
  """Runs the script.

  If the target is linux-*, download the source code and build the adb
  executable. If the target is win-* or mac-*, download the pre-built adb
  executable.
  """
  if target.startswith('linux-'):
    _download_adb_source(force)
    _build_adb(target, force)
  else:
    _download_adb(target, force)


def main():
  # Disable line buffering for SimpleTimer.
  sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

  parser = argparse.ArgumentParser()
  targets = GCC_NAMES.keys() + DEVTOOLS_URLS.keys()
  parser.add_argument('--force', '-f', action='store_true',
                      help='Ignore STAMP and force rebuild/download')
  parser.add_argument('--target', choices=targets, required=True,
                      help='Build or download adb')
  options = parser.parse_args()

  run(options.target, options.force)


if __name__ == '__main__':
  sys.exit(main())
