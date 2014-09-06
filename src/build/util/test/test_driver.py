# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess
import sys
import threading

TEST_SUITE_MAX_RETRY_COUNT = 5


class TestDriver(object):
  """Runs the given tests on test suite.

  This is a helper class to be used with test runner, where the test suite
  contains multiple tests, some of which may be flaky. This class tracks
  what needs to be run, and matches up the actual result of each test with its
  expected result.  It will then rerun the suite if necessary.
  """

  # This lock is needed to make accessing global data thread safe.
  _global_data_lock = threading.Lock()

  # This counter is shared by all instances of this class, which may be used in
  # several threads.
  _global_retry_timeout_run_count = 1

  @classmethod
  def set_global_retry_timeout_run_count(cls, value):
    cls._global_retry_timeout_run_count = value

  def __init__(self, suite_runner, test_expectations, tests_to_run, try_count,
               stop_on_unexpected_failures):
    self._suite_runner = suite_runner
    self._test_expectations = test_expectations.copy()
    self._tests_to_run = tests_to_run
    self._run_remaining_count = try_count if tests_to_run else 0
    self._stop_on_unexpected_failures = stop_on_unexpected_failures
    self._first_raw_output = ''

    # Mark planned tests INCOMPLETE to distinguish them from skipped tests.
    self.scoreboard.reset_results(self._tests_to_run)

    # Whether or not this test has been finalized.
    # finalize() can be called on testing thread (in common case) or the main
    # thread (on timeout), sometimes on both (edge case). So, mutex lock is
    # needed.
    self._finalized_lock = threading.Lock()
    self._finalized = False

  @property
  def name(self):
    return self._suite_runner.name

  @property
  def deadline(self):
    return self._suite_runner.deadline

  @property
  def tests_to_run(self):
    return self._tests_to_run

  @property
  def done(self):
    return self._run_remaining_count == 0

  @property
  def scoreboard(self):
    return self._suite_runner.get_scoreboard()

  @property
  def raw_output(self):
    return self._first_raw_output

  def terminate(self):
    self._suite_runner.terminate()

  def kill(self):
    self._suite_runner.kill()

  def prepare(self, args):
    # There are no tests to run so skip preparations.
    if self.done:
      return

    try:
      self._suite_runner.prepare_to_run(self._tests_to_run, args)
    except subprocess.CalledProcessError as e:
      print "Error preparing to run test %s (%s)\nOutput was:\n%s" % (
          self._suite_runner.name, e,
          self._suite_runner._get_subprocess_output())
      self._run_remaining_count = 0

  def _update_run_count(self):
    self._run_remaining_count -= 1

    # If we encountered tests that failed unexpectedly, that is enough to report
    # a result.
    if self.scoreboard.unexpected_failed and self._stop_on_unexpected_failures:
      self._run_remaining_count = 0

    flakes = self.scoreboard.get_flaky_tests()
    blacklist = self.scoreboard.get_incomplete_blacklist()
    did_not_run = [name for name in self.scoreboard.get_incomplete_tests()
                   if name not in blacklist]

    # TODO(lpique): We need to figure out and fix what is going on that we are
    # encountering so many timeouts. This logic is temporary and I've added it
    # to help keep the build green. At this time (20140124) we are experiencing
    # some sort of flakes where some test suites may timeout causing the build
    # to go red. Retrying the same build may make it go green, or a different
    # suite may timeout keeping the build red.
    #
    # If we encountered tests that did not complete, we will retry them as long
    # as we have not done this too often
    if did_not_run and self._run_remaining_count > 0:
      with self._global_data_lock:
        self._global_retry_timeout_run_count -= 1
        if self._global_retry_timeout_run_count < 0:
          self._run_remaining_count = 0
          return

    # Run again, retrying only the tests that require it.
    self._tests_to_run = flakes + did_not_run

    # If we are out of tests to run, we are done.
    if not self._tests_to_run:
      self._run_remaining_count = 0

  def run(self, args):
    tests_remaining_history = [sys.maxint] * TEST_SUITE_MAX_RETRY_COUNT
    self.scoreboard.register_tests(self._tests_to_run)

    while not self.done and not self._suite_runner.terminated:
      output, results = self._suite_runner.run_with_setup(self._tests_to_run,
                                                          args)
      if not self._first_raw_output:
        self._first_raw_output = output

      self._update_run_count()

      if not self.done:
        # Ensure that we will not get stuck retrying the same tests over and
        # over. The number of tests left must decrease after a certain number of
        # runs.
        current_count = len(self._tests_to_run)
        tests_remaining_history.append(current_count)

        if self._suite_runner.terminated:
          break
        if current_count < tests_remaining_history.pop(0):
          self._suite_runner.restart(self._tests_to_run, args)
        else:
          self._suite_runner.abort(self._tests_to_run, args)
          break

  def finalize(self, args):
    with self._finalized_lock:
      if self._finalized:
        return
      self._finalized = True
    self._suite_runner.finalize_after_run(self._tests_to_run, args)
