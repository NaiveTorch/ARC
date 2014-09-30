# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implements a suite runner that runs unittests."""

import util.test.suite_runner


class UnittestRunner(util.test.suite_runner.SuiteRunnerBase):
  def __init__(self, test_name, **kwargs):
    super(UnittestRunner, self).__init__(test_name, **kwargs)

  def run(self, unused_test_methods_to_run):
    test_name = self._name.replace('unittest.', '', 1)
    return self.run_subprocess_test(
        ['python', 'src/build/util/test/run_unittest.py', test_name])
