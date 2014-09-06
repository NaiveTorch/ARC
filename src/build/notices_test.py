#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests covering notices"""

import os
import unittest

from notices import Notices

_PATH_PREFIX = 'src/build/tests/notices'


def _prefix(pathlist):
  return [os.path.join(_PATH_PREFIX, p) for p in pathlist]


def _unprefix(pathlist):
  return [os.path.relpath(p, _PATH_PREFIX) for p in pathlist]


class TestNotices(unittest.TestCase):
  def __init__(self, *args, **kwargs):
    super(TestNotices, self).__init__(*args, **kwargs)
    self._n = Notices()

  def _add_sources(self, subpaths):
    self._n.add_sources(_prefix(subpaths))

  def _get_notice_roots(self):
    return _unprefix(self._n.get_notice_roots())

  def _get_license_roots(self):
    return _unprefix(self._n.get_license_roots())

  def _get_source_required_roots(self):
    return _unprefix(self._n.get_source_required_roots())

  def _get_source_required_examples(self):
    return _unprefix(self._n.get_source_required_examples())

  def _assert_roots_are(self, expect_roots, expect_source_required_roots=None):
    self.assertSetEqual(set(self._get_notice_roots()), set(expect_roots))
    if expect_source_required_roots is None:
      expect_source_required_roots = []
    self.assertSetEqual(set(self._get_source_required_roots()),
                        set(expect_source_required_roots))

  def _check_license_kind(self, p, kind):
    self.assertEquals(self._n.get_license_kind(os.path.join(_PATH_PREFIX, p)),
                      kind)

  def test_base_case(self):
    self.assertFalse(self._n.has_proper_metadata())
    self._assert_roots_are([])

  def test_simple_single_file(self):
    self._add_sources(['file.c'])
    self._assert_roots_are(['.'])
    self.assertTrue(self._n.has_proper_metadata())

  def test_nested_notice(self):
    self._add_sources(['subdir-unrestricted/file.c'])
    self._assert_roots_are(['subdir-unrestricted'])

  def test_nested_notices(self):
    self._add_sources(['file.c', 'subdir-unrestricted/file.c'])
    self._assert_roots_are(['.', 'subdir-unrestricted'])

  def _check_licenses_by_kind(self, dirs, kind, is_source_required):
    for p in dirs:
      self._n = Notices()
      self._add_sources([os.path.join(p, 'file.c')])
      if is_source_required:
        self._assert_roots_are([p], [p])
      else:
        self._assert_roots_are([p])
      self._check_license_kind(p, kind)

  def test_gpl_license(self):
    self._check_licenses_by_kind(
        ['subdir-gnu-public-license'], Notices.KIND_GPL_LIKE, True)
    self.assertTrue(self._n.has_lgpl_or_gpl())

  def test_lgpl_license(self):
    self._check_licenses_by_kind(
        ['subdir-library-gnu-public-license'], Notices.KIND_LGPL_LIKE, True)
    self.assertTrue(self._n.has_lgpl_or_gpl())

  def test_open_source_required_licenses(self):
    self._check_licenses_by_kind(
        ['subdir-mozilla-public-license',
         'subdir-creative-commons-sharealike'],
        Notices.KIND_OPEN_SOURCE_REQUIRED, True)
    self.assertFalse(self._n.has_lgpl_or_gpl())

  def test_default_licenses(self):
    self._check_licenses_by_kind(['.'], Notices.KIND_DEFAULT, False)

  def test_public_domain_license(self):
    self._check_licenses_by_kind(['subdir-public'],
                                 Notices.KIND_PUBLIC_DOMAIN, False)

  def test_notice_licenses(self):
    self._check_licenses_by_kind(
        ['subdir-either-or'], Notices.KIND_NOTICE, False)

  def test_unknown_license(self):
    self._check_licenses_by_kind(
        ['subdir-no-clue'], Notices.KIND_UNKNOWN, True)

  def test_todo_license(self):
    self._check_licenses_by_kind(['subdir-to-do'], Notices.KIND_TODO, True)

  def test_add_notices(self):
    self._add_sources(['subdir-unrestricted/file.c'])
    self._assert_roots_are(['subdir-unrestricted'])
    n1 = self._n
    self._n = Notices()
    self._add_sources(['subdir-gnu-public-license/file1.c'])
    self._assert_roots_are(['subdir-gnu-public-license'],
                           ['subdir-gnu-public-license'])
    self._n.add_notices(n1)
    self._assert_roots_are(['subdir-unrestricted', 'subdir-gnu-public-license'],
                           ['subdir-gnu-public-license'])

  def test_get_notice_files(self):
    self._add_sources(['file.c', 'subdir-unrestricted/file.c'])
    self.assertSetEqual(set(_unprefix(self._n.get_notice_files())),
                        set(['NOTICE', 'subdir-unrestricted/NOTICE']))

  def test_inheritance_license_and_inherited_notice(self):
    self._add_sources(['subdir-inherit/file.c'])
    self._assert_roots_are(['.'], ['subdir-inherit'])
    self._check_license_kind('subdir-inherit',
                             Notices.KIND_LGPL_LIKE)
    self.assertEqual(len(self._n.get_notice_files()), 1)

  def test_inheritance_notice_and_inherited_license(self):
    self._add_sources(['subdir-inherit/dir/file.c'])
    self._assert_roots_are(['subdir-inherit/dir'], ['subdir-inherit'])
    self.assertEqual(len(self._n.get_notice_files()), 1)

  def test_inheritance_overridden_license_and_inherited_notice(self):
    self._add_sources(['subdir-inherit/dir/dir/file.c'])
    self._assert_roots_are(['subdir-inherit/dir'])
    self.assertEqual(len(self._n.get_notice_files()), 1)
    self.assertListEqual(self._get_license_roots(),
                         ['subdir-inherit/dir/dir'])

  def test_multiple_notice_none_restrictive(self):
    self._add_sources(['subdir-multiple/equals/file.c'])
    self._assert_roots_are(['subdir-multiple/equals'])

  def test_multiple_notice_one_restrictive(self):
    self._add_sources(['subdir-multiple/diff/file.c'])
    self._assert_roots_are(['subdir-multiple/diff'], ['subdir-multiple/diff'])

  def test_get_most_restrictive_license_kind(self):
    self.assertEqual(self._n.get_most_restrictive_license_kind(),
                     Notices.KIND_PUBLIC_DOMAIN)
    self._add_sources(['subdir-library-gnu-public-license/file.c'])
    self.assertEqual(self._n.get_most_restrictive_license_kind(),
                     Notices.KIND_LGPL_LIKE)
    self._add_sources(['subdir-mozilla-public-license/file.c'])
    self.assertEqual(self._n.get_most_restrictive_license_kind(),
                     Notices.KIND_LGPL_LIKE)
    self._add_sources(['subdir-gnu-public-license/file.c'])
    self.assertEqual(self._n.get_most_restrictive_license_kind(),
                     Notices.KIND_GPL_LIKE)


if __name__ == '__main__':
  unittest.main()
