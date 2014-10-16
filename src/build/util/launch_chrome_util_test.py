#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from util import launch_chrome_util


class IsLaunchChromeCommandTest(unittest.TestCase):
  def test_xvfb(self):
    args = ['xvfb-run', '--auto-servernum', '--server-args',
            '-screen 0 640x480x24',
            '--error-file', '/some/output.log', '/bin/sh', 'launch_chrome',
            'run', 'this-app.apk', '--with-this-option']
    self.assertTrue(launch_chrome_util.is_launch_chrome_command(args))
    self.assertEqual(['run', 'this-app.apk', '--with-this-option'],
                     launch_chrome_util.remove_leading_launch_chrome_args(args))

    args = ['xvfb-run', '--auto-servernum', '--server-args',
            '-screen 0 640x480x24',
            '--error-file', '/some/output.log', 'do-something-else']
    self.assertFalse(launch_chrome_util.is_launch_chrome_command(args))

  def test_normal(self):
    args = ['/bin/sh', 'launch_chrome', 'run', 'whatever']
    self.assertTrue(launch_chrome_util.is_launch_chrome_command(args))
    self.assertEqual(['run', 'whatever'],
                     launch_chrome_util.remove_leading_launch_chrome_args(args))

  def test_not_launch_chrome(self):
    args = ['gcc', '-c', 'whatever']
    self.assertFalse(launch_chrome_util.is_launch_chrome_command(args))


if __name__ == '__main__':
  unittest.main()
