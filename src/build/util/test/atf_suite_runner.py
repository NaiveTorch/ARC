# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implements a simple ARC ATF Suite test runner."""

import launch_chrome_options
import prep_launch_chrome
from util.test.suite_runner import SuiteRunnerBase


class AtfSuiteRunner(SuiteRunnerBase):
  def __init__(self, test_name, test_args, **kwargs):
    super(AtfSuiteRunner, self).__init__(test_name, **kwargs)
    self.set_test_args(test_args)

  def set_test_args(self, test_args):
    self._test_args = test_args

  def get_launch_chrome_command_for_atf(self):
    return self.get_launch_chrome_command(['atftest'] + list(self._test_args))

  def prepare(self, unused_test_methods_to_run):
    args = self.get_launch_chrome_command_for_atf()
    prep_launch_chrome.prepare_crx_with_raw_args(args)

  def run(self, unused_test_methods_to_run):
    args = self.get_launch_chrome_command_for_atf()
    # The CRX is built in prepare, so it is unnecessary build here.
    args.append('--nocrxbuild')
    return self.run_subprocess_test(args)

  def finalize(self, unused_test_methods_to_run):
    # Use the args as those of prepare to run remove_crx_at_exit_if_needed in
    # the same condition.
    args = self.get_launch_chrome_command_for_atf()
    parsed_args = launch_chrome_options.parse_args(args)
    # Removing the CRX is deferred in case this is running for the remote
    # execution, which needs to copy all the CRXs after all the suite runners
    # in the local host have finished.
    prep_launch_chrome.remove_crx_at_exit_if_needed(parsed_args)
