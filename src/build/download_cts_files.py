#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import os
import os.path
import subprocess
import sys

import build_common
import download_common


_ROOT_DIR = build_common.get_arc_root()


class BaseAndroidCTSDownload(download_common.BaseGetAndUnpackArchiveFromURL):
  """Handles syncing a pre-built Android CTS zip file package."""

  @classmethod
  def _unpack_update(cls, download_file):
    subprocess.check_call(['unzip', '-d', cls.STAGE_DIR, download_file])


class AndroidCTSBaseFiles(BaseAndroidCTSDownload):
  """The full ready-built .apk files and .xml files describing the tests."""
  NAME = 'Android CTS'
  DEPS_FILE = os.path.join(_ROOT_DIR, 'src', 'build', 'DEPS.android-cts')
  FINAL_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-cts')
  STAGE_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-cts.bak')
  DOWNLOAD_NAME = 'cts.zip'


class AndroidCTSMediaFiles(BaseAndroidCTSDownload):
  """Approx 1Gb of data specific to the media tests."""
  NAME = 'Android CTS Media'
  DEPS_FILE = os.path.join(_ROOT_DIR, 'src', 'build', 'DEPS.android-cts-media')
  FINAL_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-cts-media')
  STAGE_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-cts-media.bak')
  DOWNLOAD_NAME = 'cts_media.zip'


def check_and_perform_updates(include_media=False):
  success = True
  success &= AndroidCTSBaseFiles.check_and_perform_update()
  if include_media:
    success &= AndroidCTSMediaFiles.check_and_perform_update()
  return not success


def main():
  description = 'Downloads Android CTS related files.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('--include-media', action='store_true',
                      default=False, dest='include_media',
                      help='Include the CTS Media files (1Gb)')

  args = parser.parse_args()

  return check_and_perform_updates(include_media=args.include_media)


if __name__ == '__main__':
  sys.exit(main())
