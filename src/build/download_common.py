# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import urllib

import build_common


def _read_stamp_file(path):
  """Returns the file content, or an empty string if not exists."""
  if not os.path.exists(path):
    return ''
  with open(path, 'r') as f:
    for line in f:
      # Ignore lines starting with #.
      if line.startswith('#'):
        continue
      # Ignore leading and trailing white spaces.
      return line.strip()


class BaseGetAndUnpackArchiveFromURL(object):
  """Handles downloading and extracting a package from a URL."""

  # Override these in a derived class
  NAME = None
  DEPS_FILE = None
  FINAL_DIR = None
  STAGE_DIR = None
  DOWNLOAD_NAME = None

  @classmethod
  def _unpack_update(cls, download_file):
    raise NotImplementedError('Please implement this in a derived class.')

  @classmethod
  def _fetch_and_stage_update(cls, url):
    """Downloads an update file to a temp directory, and manages replacing the
    final directory with the stage directory contents."""

    result = True
    try:
      tmp_dir = tempfile.mkdtemp(suffix='.tmp', prefix=cls.DOWNLOAD_NAME)
      try:
        shutil.rmtree(cls.STAGE_DIR, ignore_errors=True)
        os.mkdir(cls.STAGE_DIR)

        download_file = os.path.join(tmp_dir, cls.DOWNLOAD_NAME)
        urllib.urlretrieve(url, download_file)

        cls._unpack_update(download_file)

        shutil.rmtree(cls.FINAL_DIR, ignore_errors=True)
        os.rename(cls.STAGE_DIR, cls.FINAL_DIR)
      finally:
        shutil.rmtree(cls.STAGE_DIR, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as e:
      print e
      result = False
    return result

  @classmethod
  def post_update_work(cls):
    """Override in derived classes to perform additional work after downloading
    and unpacking the download."""
    return True

  @classmethod
  def check_and_perform_update(cls):
    """Checks the current and dependency stamps, and performs the update if
    they are different."""

    url = _read_stamp_file(cls.DEPS_FILE)
    stamp_file = build_common.StampFile(
        url, os.path.join(cls.FINAL_DIR, 'URL'))
    if stamp_file.is_up_to_date():
      return True

    print 'INFO: Updating %s...' % cls.NAME
    if not cls._fetch_and_stage_update(url):
      print 'Failed to update %s.' % cls.NAME
      return False

    stamp_file.update()
    result = cls.post_update_work()
    print 'INFO: Done'
    return result
