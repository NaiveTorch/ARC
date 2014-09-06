#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for staging."""

import unittest

import staging


class StagingTest(unittest.TestCase):
  def test_is_in_staging(self):
    self.assertTrue(staging.is_in_staging('src'))
    self.assertTrue(staging.is_in_staging('src/common'))
    self.assertTrue(staging.is_in_staging('android'))
    self.assertTrue(staging.is_in_staging('android/frameworks/base'))
    self.assertTrue(staging.is_in_staging('libyuv'))
    self.assertTrue(staging.is_in_staging('chromium-ppapi'))
    self.assertFalse(staging.is_in_staging('canned'))
    self.assertFalse(staging.is_in_staging('__non_existent_directory__'))

  def test_get_default_tracking_path(self):
    self.assertEquals(
        'third_party/android/frameworks/base',
        staging.get_default_tracking_path('mods/android/frameworks/base'))
    self.assertEquals(
        'internal/third_party/internal_component',
        staging.get_default_tracking_path('internal/mods/internal_component'))
    self.assertEquals(
        'src/build/tests/analyze_diffs/third_party/AndroidManifest.xml',
        staging.get_default_tracking_path(
            'src/build/tests/analyze_diffs/mods/AndroidManifest.xml'))

  def test_as_staging(self):
    self.assertEquals('out/staging/android/frameworks/base',
                      staging.as_staging('android/frameworks/base'))
    self.assertEquals('out/staging/src/common',
                      staging.as_staging('src/common'))

  def test_as_real_path(self):
    self.assertEquals(
        'mods/android/NOTICE',
        staging.as_real_path('android/NOTICE'))
    self.assertEquals(
        'third_party/chromium-ppapi/ppapi/LICENSE',
        staging.as_real_path('chromium-ppapi/ppapi/LICENSE'))

  def test_third_party_to_staging(self):
    self.assertEquals(
        'out/staging/android/frameworks/base',
        staging.third_party_to_staging('third_party/android/frameworks/base'))
    # This is just for testing staging.third_party_to_staging. In reality we
    # cannot use the name that exists under third_party directory.
    self.assertEquals(
        'out/staging/android',
        staging.third_party_to_staging('internal/third_party/android'))

  def test_get_composite_paths_unknown(self):
    third, mods = staging.get_composite_paths('foo/bar')
    self.assertEquals(None, third)
    self.assertEquals(None, mods)

  def test_get_composite_paths_known(self):
    third, mods = staging.get_composite_paths('out/staging/foo/bar')
    self.assertEquals('third_party/foo/bar', third)
    self.assertEquals('mods/foo/bar', mods)


if __name__ == '__main__':
  unittest.main()
