#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests covering open_source management"""

import open_source
import os
import unittest

_PATH_PREFIX = 'src/build/tests/open_source'


class TestOpenSource(unittest.TestCase):
  RULES = ['foobar.c*', 'subdir']

  def test_open_source_repo(self):
    # We do not run tests in the open source repo.
    self.assertFalse(open_source.is_open_source_repo())

  def test_is_basename_open_sourced_true(self):
    for p in ['foobar.c', 'foobar.cpp', 'subdir']:
      self.assertTrue(open_source.is_basename_open_sourced(p, self.RULES))

  def test_is_basename_open_sourced_false(self):
    for p in ['', 'other', 'foobar.h', 'xfoobar.c', 'subdir2']:
      self.assertFalse(open_source.is_basename_open_sourced(p, self.RULES))

  def test_is_basename_open_sourced_bang_means_not(self):
    self.assertFalse(open_source.is_basename_open_sourced('!foo', ['!foo']))

  def test_is_basename_open_sourced_conflict(self):
    def _test_in_and_out(rules):
      self.assertTrue(open_source.is_basename_open_sourced('in', rules))
      self.assertFalse(open_source.is_basename_open_sourced('out', rules))

    def _test_out_and_out2(rules):
      self.assertFalse(open_source.is_basename_open_sourced('out', rules))
      self.assertFalse(open_source.is_basename_open_sourced('out2', rules))

    self.assertFalse(open_source.is_basename_open_sourced('foo',
                                                          ['foo', '!foo']))
    _test_in_and_out(['*', '!out'])
    _test_in_and_out(['!out', '*'])
    _test_in_and_out(['in', 'out', '!out'])
    _test_out_and_out2(['out', '!*'])
    _test_out_and_out2(['!*', 'out'])

  def test_is_open_sourced_true(self):
    for p in ['yes', 'yes/anything.c', 'selective/foobar.c',
              'selective/foobar.cpp', 'selective/subdir/file.c']:
      self.assertTrue(open_source.is_open_sourced(
          os.path.join(_PATH_PREFIX, p)))

  def test_is_open_sourced_false(self):
    for p in ['no', 'no/file.c', 'selective/xfoobar.c',
              'selective/subdir2/file.c']:
      self.assertFalse(open_source.is_open_sourced(
          os.path.join(_PATH_PREFIX, p)))

  def test_is_third_party_open_sourced_true(self):
    for p in ['third_party/android']:
      self.assertTrue(open_source.is_open_sourced(p))
