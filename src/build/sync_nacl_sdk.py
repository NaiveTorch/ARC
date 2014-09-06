#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Syncs the nacl sdk at a pinned version given in NACLSDK.json

import argparse
import filecmp
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib

import build_common


_ROOT_DIR = build_common.get_arc_root()
_NACL_SDK_DIR = os.path.join(_ROOT_DIR, 'third_party', 'nacl_sdk')
_STAMP_PATH = os.path.join(_NACL_SDK_DIR, 'STAMP')
_PINNED_MANIFEST = os.path.join(_ROOT_DIR, 'src', 'build', 'DEPS.naclsdk')
_NACL_MIRROR = 'https://commondatastorage.googleapis.com/nativeclient-mirror'
_LATEST_MANIFEST_URL = _NACL_MIRROR + '/nacl/nacl_sdk/naclsdk_manifest2.json'
_NACL_SDK_ZIP_URL = _NACL_MIRROR + '/nacl/nacl_sdk/nacl_sdk.zip'


def _log_check_call(log_function, *args, **kwargs):
  """Log each line of output from a command.

  Args:
    log_function: Function to call to log.
    *args: Ordered args.
    **kwargs: Keyword args.
  """
  p = subprocess.Popen(
      *args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
  for line in p.stdout:
    log_function(line.rstrip())
  return_code = p.wait()
  if return_code:
    # Unlike subprocess.check_call, as we do not use 'args' kw-arg in this
    # module, we do not check it.
    cmd = args[0]
    raise subprocess.CalledProcessError(cmd, return_code)


def _roll_forward_pinned_manifest():
  """Roll forward the pinned manifest to the latest version."""
  logging.info('Rolling forward the pinned NaCl manifest...')
  urllib.urlretrieve(_LATEST_MANIFEST_URL, _PINNED_MANIFEST)
  logging.info('Done.')


def _should_delete_nacl_sdk():
  """Returns True if the SDK tree should be deleted."""
  if not os.path.exists(_STAMP_PATH):
    return False
  # Returns true if _PINNED_MANIFEST is modified. This is necessary because
  # './naclsdk update' does nothing when _PINNED_MANIFEST is reverted back
  # to an older revision. We use filecmp.cmp() rather than parsing the manifest
  # file. Since deleting the SDK is relatively cheap, and updating the SDK is
  # as slow as installing it from scratch, just comparing files would be okay.
  return not filecmp.cmp(_PINNED_MANIFEST, _STAMP_PATH)


def _update_nacl_sdk():
  """Download and sync the NaCl SDK."""
  if _should_delete_nacl_sdk():
    # Deleting the obsolete SDK tree usually takes only <1s.
    logging.info('Deleting old NaCl SDK...')
    shutil.rmtree(_NACL_SDK_DIR)

  # Download sdk zip if needed. The zip file only contains a set of Python
  # scripts that download the actual SDK. This step usually takes only <1s.
  if (not os.path.exists(_NACL_SDK_DIR) or
      not os.path.exists(os.path.join(_NACL_SDK_DIR, 'naclsdk'))):
    logging.info('NaCl SDK Updater not present, downloading...')
    work_dir = tempfile.mkdtemp(suffix='.tmp', prefix='naclsdk')
    try:
      zip_path = os.path.join(work_dir, 'nacl_sdk.zip')
      urllib.urlretrieve(_NACL_SDK_ZIP_URL, zip_path)
      logging.info('Extracting...')
      build_common.makedirs_safely(_NACL_SDK_DIR)
      _log_check_call(
          logging.info, ['unzip', zip_path],
          cwd=os.path.dirname(_NACL_SDK_DIR))
    except:
      logging.error('Extracting SDK Updater failed, cleaning up...')
      shutil.rmtree(_NACL_SDK_DIR, ignore_errors=True)
      logging.error('Cleaned up.')
      raise
    finally:
      shutil.rmtree(work_dir)
    logging.info('Done.')

  # Update based on pinned manifest. This part can be as slow as 1-2 minutes
  # regardless of whether it is a fresh install or an update.
  start = time.time()
  logging.info('Updating NaCl SDK...')
  _log_check_call(
      logging.info, ['./naclsdk', 'update', '-U', 'file://' + _PINNED_MANIFEST,
                     '--force', 'pepper_canary'],
      cwd=_NACL_SDK_DIR)
  total_time = time.time() - start
  if total_time > 1:
    print 'NaCl SDK update took %0.3fs' % total_time
  else:
    logging.info('Done. [%fs]' % total_time)


def _update_stamp():
  """Update a stamp file for build tracking."""
  shutil.copyfile(_PINNED_MANIFEST, _STAMP_PATH)


def main(args):
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbose', action='store_true', help='Emit '
                      'verbose output.')
  parser.add_argument('-r', '--roll-forward', dest='roll', action='store_true',
                      help='Update pinned NaCl SDK manifest version to the '
                      'latest..')
  args = parser.parse_args(args)

  if args.verbose:
    level = logging.DEBUG
  else:
    level = logging.WARNING
  logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

  if args.roll:
    _roll_forward_pinned_manifest()
  _update_nacl_sdk()
  _update_stamp()

  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
