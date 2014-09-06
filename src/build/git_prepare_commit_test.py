#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import git_prepare_commit


class TestGitPrepareCommit(unittest.TestCase):
  def test_add_mandatory_lines(self):
    self.assertEqual(
        ['\n', 'TEST=\n', 'PERF=\n', 'BUG=\n', '\n'],
        git_prepare_commit.add_mandatory_lines([]))
    self.assertEqual(
        ['\n', 'TEST=\n', 'PERF=\n', 'BUG=\n', '\n', '# comment\n'],
        git_prepare_commit.add_mandatory_lines(['# comment\n']))
    self.assertEqual(
        ['TEST=foobar\n', 'PERF=N/A\n', 'BUG=999999\n', '# comment\n'],
        git_prepare_commit.add_mandatory_lines(
            ['TEST=foobar\n', 'PERF=N/A\n', 'BUG=999999\n', '# comment\n']))
    # Only nonexistent prefixes should be inserted.
    self.assertEqual(
        ['TEST=foobar\n', 'PERF=N/A\n', 'BUG=\n', '\n', 'Change-Id:'],
        git_prepare_commit.add_mandatory_lines(
            ['TEST=foobar\n', 'PERF=N/A\n', '\n', 'Change-Id:']))

  def test_get_changed_files(self):
    commit_lines = '''foobar

TEST=something

# Changes to be committed:
#       new file: path/to/added_file
#       modified: path/to/modified_file
#        renamed: path/to/src_file -> path/to/dest_file
#       modified: mods/path/to/chromium/modified_file
#       modified: mods/path/to/android/modified_file
#
# Untracked files:
# ...'''.splitlines()
    self.assertEqual(['path/to/added_file',
                      'path/to/modified_file',
                      'mods/path/to/android/modified_file'],
                     git_prepare_commit.get_changed_files(commit_lines))

  def test_get_bug_ids_from_diff(self):
    diffs = ['''diff --git a/path/to/x b/path/to/x
index 1d91473..f56a7aa 100755
--- a/path/to/x
+++ b/path/to/x
@@ -44,9 +44,9 @@ something
 crbug.com/111111

+ crbug.com/222222
+ crbug.com/333333
- crbug.com/333333
- crbug.com/444444
- crbug.com/555555
- crbug.com/666666
- crbug.com/invalid

''',
             '''diff --git a/path/to/x b/path/to/x
index 1d91473..f56a7aa 100755
--- a/path/to/x
+++ b/path/to/x
@@ -44,9 +44,9 @@ something
+ crbug.com/666666
''']
    self.assertEqual(set(('444444', '555555')),
                     git_prepare_commit.get_bug_ids_from_diffs(diffs))

  def test_update_bug_line(self):
    self.assertEqual(
        ['foobar\n', 'BUG=111111, 222222\n'],
        git_prepare_commit.update_bug_line(['foobar\n', 'BUG=\n'],
                                           set(('111111', '222222'))))
    self.assertEqual(
        ['BUG=333333\n', '# Suggestion: BUG=111111, 222222, 333333\n'],
        git_prepare_commit.update_bug_line(['BUG=333333\n'],
                                           set(('111111', '222222'))))
    # There must not be duplicated IDs.
    self.assertEqual(
        ['BUG=222222, 333333\n', '# Suggestion: BUG=111111, 222222, 333333\n'],
        git_prepare_commit.update_bug_line(['BUG=333333, 222222\n'],
                                           set(('111111', '222222'))))

    # Nothing should be done when no bug ID is specified.
    self.assertEqual(
        ['BUG=N/A\n'],
        git_prepare_commit.update_bug_line(['BUG=N/A\n'], set()))
    self.assertEqual(
        ['BUG=\n'],
        git_prepare_commit.update_bug_line(['BUG=\n'], set()))

    # N/A or None should be replaced when there is actually a bug.
    self.assertEqual(
        ['BUG=111111, 222222\n'],
        git_prepare_commit.update_bug_line(['BUG=N/A\n'],
                                           set(('111111', '222222'))))
    self.assertEqual(
        ['BUG=111111, 222222\n'],
        git_prepare_commit.update_bug_line(['BUG=nOnE\n'],
                                           set(('111111', '222222'))))

    # Unknown type of bug description should be preserved.
    self.assertEqual(
        ['BUG=native_client:3456\n',
         '# Suggestion: BUG=111111, native_client:3456\n'],
        git_prepare_commit.update_bug_line(['BUG=native_client:3456\n'],
                                           set(['111111'])))

    # When no BUG= line is found, do nothing.
    self.assertEqual(
        ['foobar'],
        git_prepare_commit.update_bug_line(['foobar'], set(['111111'])))


if __name__ == '__main__':
  unittest.main()
