#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import io
import os
import select
import subprocess
import sys

import build_common
import download_common
import toolchain

_ROOT_DIR = build_common.get_arc_root()


class BaseAndroidCompressedTarDownload(
    download_common.BaseGetAndUnpackArchiveFromURL):
  """Handle syncing Android source code packages in compressed tar forms."""

  @classmethod
  def _unpack_update(cls, download_file):
    subprocess.check_call(['tar', '--extract',
                           '--use-compress-program=' + cls.COMPRESSION_PROGRAM,
                           '--directory=' + cls.STAGE_DIR,
                           '--strip-components=1',
                           '--file=' + download_file])


class AndroidNDKFiles(BaseAndroidCompressedTarDownload):
  """The Android NDK."""
  NAME = 'Android NDK'
  DEPS_FILE = os.path.join(_ROOT_DIR, 'src', 'build', 'DEPS.ndk')
  FINAL_DIR = os.path.join(_ROOT_DIR, 'third_party', 'ndk')
  STAGE_DIR = os.path.join(_ROOT_DIR, 'third_party', 'ndk.bak')
  DOWNLOAD_NAME = 'ndk.tar.bz2'
  COMPRESSION_PROGRAM = 'pbzip2'


class AndroidSDKFiles(BaseAndroidCompressedTarDownload):
  """The Android SDK."""
  NAME = 'Android SDK'
  DEPS_FILE = os.path.join(_ROOT_DIR, 'src', 'build', 'DEPS.android-sdk')
  FINAL_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-sdk')
  STAGE_DIR = os.path.join(_ROOT_DIR, 'third_party', 'android-sdk.bak')
  DOWNLOAD_NAME = 'sdk.tgz'
  COMPRESSION_PROGRAM = 'pigz'
  API_TAG = 'API 17'
  # This tag is used for downloading the default version, which may be newer
  # than the pinned version defined in toolchain.py.
  SDK_BUILD_TOOLS_TAG = 'Android SDK Build-tools'

  @classmethod
  def post_update_work(cls):
    android_tool = os.path.join(cls.FINAL_DIR, 'tools', 'android')
    packages = subprocess.Popen([android_tool, 'list', 'sdk'],
                                stdout=subprocess.PIPE).communicate()[0]
    filters = ['platform-tools']
    for line in packages.split('\n'):
      if cls.API_TAG in line or cls.SDK_BUILD_TOOLS_TAG in line:
        ind = line.find('-')
        if ind > 0:
          filters.append(line[:ind].strip())
    assert len(filters) >= 3, 'No "%s" or "%s" packages found' % (
        cls.API_TAG, cls.SDK_BUILD_TOOLS_TAG)

    return AndroidSDKFiles._update_sdk(android_tool, filters)

  @staticmethod
  def _update_sdk(android_tool, filters, extra_args=None):
    args = [android_tool, 'update', 'sdk', '--no-ui',
            '--filter', ','.join(filters)]
    if extra_args:
      args.extend(extra_args)

    p = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    p.stdout = AndroidSDKFiles._reopen_without_buffering(p.stdout)
    p.stderr = AndroidSDKFiles._reopen_without_buffering(p.stderr)
    streams = [p.stdout, p.stderr]
    current_line = ''
    while True:
      rset, _, _ = select.select([p.stdout, p.stderr], [], [])
      for stream in streams:
        if stream not in rset:
          continue
        new_fragment = os.read(stream.fileno(), 4096)
        if not new_fragment:
          stream.close()
          continue
        current_line = AndroidSDKFiles._process_sdk_update_output_fragment(
            p, current_line + new_fragment)
      if p.poll() is not None:
        break
    if p.wait() != 0:
      raise subprocess.CalledProcessError(p.returncode, args)

    return True

  @staticmethod
  def _process_sdk_update_output_fragment(p, fragment):
    # Look for the last newline, and split there
    if '\n' in fragment:
      completed, remaining = fragment.rsplit('\n', 1)
      if completed:
        sys.stdout.write(completed + '\n')
    else:
      remaining = fragment
    if remaining.startswith('Do you accept the license '):
      sys.stdout.write(remaining)
      p.stdin.write('y\n')
      remaining = ''
    return remaining

  @staticmethod
  def _reopen_without_buffering(stream):
    if not stream:
      return None
    new_stream = io.open(os.dup(stream.fileno()), mode='rb', buffering=0)
    stream.close()
    return new_stream

  @classmethod
  def check_and_perform_pinned_build_tools_update(cls):
    """Checks and performs update for the pinned build-tools."""
    pinned_version = toolchain.get_android_sdk_build_tools_pinned_version()
    pinned_id = 'build-tools-' + pinned_version
    pinned_dir = os.path.join(cls.FINAL_DIR, 'build-tools', pinned_version)
    if not os.path.exists(pinned_dir):
      android_tool = os.path.join(cls.FINAL_DIR, 'tools', 'android')
      filters = [pinned_id]
      # Add --all so that the bulid tools package is selected even if it's
      # obsolete or newer than the installed version.
      extra_args = ['--all']
      return AndroidSDKFiles._update_sdk(android_tool, filters, extra_args)
    return True


def check_and_perform_updates(include_media=False):
  success = True
  success &= AndroidNDKFiles.check_and_perform_update()
  success &= AndroidSDKFiles.check_and_perform_update()
  success &= AndroidSDKFiles.check_and_perform_pinned_build_tools_update()
  return not success


def main():
  return check_and_perform_updates()


if __name__ == '__main__':
  sys.exit(main())
