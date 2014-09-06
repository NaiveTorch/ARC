# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

from util.test import suite_results
from util.test.scoreboard_constants import EXPECT_FAIL
from util.test.scoreboard_constants import EXPECT_PASS
from util.test.scoreboard_constants import FLAKE
from util.test.scoreboard_constants import INCOMPLETE
from util.test.scoreboard_constants import SKIPPED
from util.test.scoreboard_constants import UNEXPECT_FAIL
from util.test.scoreboard_constants import UNEXPECT_PASS
from util.test.suite_runner_config_flags import FAIL
from util.test.suite_runner_config_flags import FLAKY
from util.test.suite_runner_config_flags import NOT_SUPPORTED
from util.test.suite_runner_config_flags import TIMEOUT


class Scoreboard:
  """A class used to track test results and overall status of a SuiteRunner."""

  # This special name is used to denote all tests that are a part of a suite.
  # This allows exceptions to be placed on all tests, rather than having
  # to specify them individually.
  # TODO(haroonq): All sorts of weird problems occur if we have a test named
  # '*'.  Unfortunately, for several tests (like the dalvik tests), we do not
  # actually have test names, so ALL_TESTS_DUMMY_NAME is being used instead.
  # Ideally, this class should not really have any 'special' test name and
  # treat all test names the same.  Instead, the expectations should be
  # expanded out by the owning class before it reaches here.
  ALL_TESTS_DUMMY_NAME = '*'

  # The (internal) expectations for individual tests.
  _SHOULD_PASS = 0
  _SHOULD_FAIL = 1
  _SHOULD_SKIP = 2
  _MAYBE_FLAKY = 3

  _MAP_EXPECTATIONS_TO_RESULT = {
      _SHOULD_FAIL: EXPECT_FAIL,
      _MAYBE_FLAKY: FLAKE,
      _SHOULD_SKIP: SKIPPED,
      _SHOULD_PASS: EXPECT_PASS,
  }

  def __init__(self, name, expectations):
    self._name = name
    self._complete_count = 0
    self._restart_count = 0
    self._start_time = None
    self._end_time = None
    self._expectations = {}
    self._results = {}

    # Once a test has not been completed twice, it will be 'blacklisted' so
    # that the SuiteRunner can skip it going forward.
    self._did_not_complete_once = set()
    self._did_not_complete_blacklist = []

    # Update the internal expectations for the tests.
    self._default_expectation = self._SHOULD_PASS
    self.set_expectations(expectations)

  def reset_results(self, tests):
    for test in tests:
      if test != self.ALL_TESTS_DUMMY_NAME:
        self._results[test] = INCOMPLETE

  def set_expectations(self, expectations):
    """
    Specify test suite expectations.

    In addition to settings expectations at creation time, additional
    expectations can be defined later once more information is known about
    the tests.
    """
    if not expectations:
      return
    for name, ex in expectations.iteritems():
      if NOT_SUPPORTED in ex:
        expectation = self._SHOULD_SKIP
      elif FLAKY in ex:
        expectation = self._MAYBE_FLAKY
      elif FAIL in ex:
        expectation = self._SHOULD_FAIL
      # Tests marked as TIMEOUT will be skipped, unless --include-timeouts is
      # specified.  Unfortunately, we have no way of knowing, so we just assume
      # they will be skipped.  If it turns out that this test is actually run,
      # then it will get treated as though it was expected to PASS.  We assume
      # the TIMEOUT is not specified with FAIL or FLAKY as well.
      elif TIMEOUT in ex:
        expectation = self._SHOULD_SKIP
      else:
        expectation = self._SHOULD_PASS
      if name == self.ALL_TESTS_DUMMY_NAME:
        self._default_expectation = expectation
      else:
        self._expectations[name] = expectation

  def register_tests(self, tests_to_run):
    """
    Call only once when the suite is being started to run with the list of
    tests that are expected to run.
    """
    self._start_time = time.time()
    suite_results.report_start(self)
    for name in tests_to_run:
      if self.ALL_TESTS_DUMMY_NAME in name:
        continue
      self._register_test(name)

  def start(self, tests_to_run):
    """
    Sets the results for the specified tests to INCOMPLETE.

    This is done even if the test has been run before since it is needed when
    rerunning flaky tests.
    """
    for name in tests_to_run:
      if self.ALL_TESTS_DUMMY_NAME in name:
        continue
      assert name in self._expectations
      self._results[name] = INCOMPLETE

  def restart(self):
    """
    Notifies the scoreboard that the tests are going to be restarted.

    This is most likely to rerun any incomplete or flaky tests.
    """
    for name, result in self._results.iteritems():
      # All remaining tests were not completed (most likely due to other
      # failures or timeouts).
      if result == INCOMPLETE:
        if name in self._did_not_complete_once:
          self._did_not_complete_blacklist.append(name)
        else:
          self._did_not_complete_once.add(name)
    self._restart_count += 1
    suite_results.report_restart(self)

  def abort(self):
    """Notifies the scoreboard that test runs are being ended prematurely."""
    suite_results.report_abort(self)

  def start_test(self, test):
    """Notifies the scoreboard that a single test is about to be run."""
    suite_results.report_start_test(self, test)

  def update(self, tests):
    """Updates the scoreboard with a list of TestMethodResults."""
    for test in tests:
      expect = self._default_expectation
      if self.ALL_TESTS_DUMMY_NAME in test.name:
        if len(self._expectations) != 0:
          continue
      else:
        self._register_test(test.name)
        expect = self._expectations[test.name]
      result = EXPECT_PASS if test and test.passed else EXPECT_FAIL
      actual = self._determine_actual_status(result, expect)
      self._set_result(test.name, actual)
      self._complete_count += 1
      suite_results.report_update_test(self, test.name, actual, test.duration)

  def finalize(self):
    """
    Notifies the scoreboard that the test suite is finished.

    It is expected that the suite will not be run again.  Any tests that did
    not run will be marked as SKIPPED and any flaky tests will be marked as
    UNEXPECT_FAIL.
    """
    for name, ex in self._expectations.iteritems():
      self._finalize_test(name, ex)
    self._end_time = time.time()
    suite_results.report_results(self)

  @property
  def name(self):
    return self._name

  @property
  def duration(self):
    start_time = self._start_time or time.time()
    end_time = self._end_time or time.time()
    return end_time - start_time

  # This is the expected total number of tests in a suite.  This value can
  # change over time (eg. as flaky tests are rerun or new tests are
  # discovered).  As such, there is no correlation between the total and the
  # completed/incompleted properties.
  @property
  def total(self):
    # If a test suite has a scoreboard, we have to assume that at least one
    # test will be run.  len(self._expectations) can be zero if only a '*'
    # expectation was specified.
    return max(self._complete_count, len(self._expectations), 1)

  @property
  def completed(self):
    return self._complete_count

  @property
  def incompleted(self):
    return len(self.get_incomplete_tests())

  @property
  def passed(self):
    return self.expected_passed + self.unexpected_passed

  @property
  def failed(self):
    return self.expected_failed + self.unexpected_failed

  @property
  def expected_passed(self):
    return self._get_count(EXPECT_PASS)

  @property
  def unexpected_passed(self):
    return self._get_count(UNEXPECT_PASS)

  @property
  def expected_failed(self):
    return self._get_count(EXPECT_FAIL)

  @property
  def unexpected_failed(self):
    return self._get_count(UNEXPECT_FAIL)

  @property
  def skipped(self):
    return self._get_count(SKIPPED)

  @property
  def restarts(self):
    return self._restart_count

  def get_flaky_tests(self):
    return self._get_list(FLAKE)

  def get_skipped_tests(self):
    return self._get_list(SKIPPED)

  def get_incomplete_tests(self):
    return self._get_list(INCOMPLETE)

  def get_expected_passing_tests(self):
    return self._get_list(EXPECT_PASS)

  def get_unexpected_passing_tests(self):
    return self._get_list(UNEXPECT_PASS)

  def get_expected_failing_tests(self):
    return self._get_list(EXPECT_FAIL)

  def get_unexpected_failing_tests(self):
    return self._get_list(UNEXPECT_FAIL)

  def _get_list(self, result):
    return [key for key, value in self._results.iteritems() if value == result]

  def _get_count(self, result):
    return self._results.values().count(result)

  def get_incomplete_blacklist(self):
    return self._did_not_complete_blacklist

  @property
  def overall_status(self):
    if self.incompleted:
      return INCOMPLETE
    elif self.unexpected_failed:
      return UNEXPECT_FAIL
    elif self.unexpected_passed:
      return UNEXPECT_PASS
    elif self.expected_failed:
      return EXPECT_FAIL
    elif self.skipped and not self.passed:
      return SKIPPED
    else:
      return EXPECT_PASS

  def _register_test(self, name):
    if not name in self._expectations:
      self._expectations[name] = self._SHOULD_PASS
      self._set_result(name, INCOMPLETE)

  def _set_result(self, name, result):
    if name in self._did_not_complete_blacklist and result != INCOMPLETE:
      self._did_not_complete_blacklist.remove(name)
    self._results[name] = result

  def _finalize_test(self, name, expect):
    assert self._is_valid_expectation(expect)

    if expect in [self._SHOULD_PASS, self._SHOULD_FAIL]:
      # This test was never started, so record and report it as being skipped.
      if name not in self._results:
        self._set_result(name, SKIPPED)
        # We are officially marking the test completed so that the total
        # tests adds up correctly.
        self._complete_count += 1
        suite_results.report_update_test(self, name, SKIPPED)
      # This test had no chance to start, or was started but never completed.
      # Report it as incomplete.
      elif self._results[name] == INCOMPLETE:
        suite_results.report_update_test(self, name, INCOMPLETE)
    # This test was expected to be skipped and we have no results (ie. it
    # really was skipped) so record and report it as such.  Note: It is
    # possible for tests that were expected to be skipped to be run.  See
    # comment about TIMEOUT above.
    elif expect == self._SHOULD_SKIP and name not in self._results:
      self._set_result(name, SKIPPED)
      suite_results.report_update_test(self, name, SKIPPED)
    # This flaky test never successfully passed, so record and report it as
    # a failure.
    elif expect == self._MAYBE_FLAKY and self._results.get(name) == FLAKE:
      self._set_result(name, UNEXPECT_FAIL)
      suite_results.report_update_test(self, name, UNEXPECT_FAIL)
    elif expect == self._MAYBE_FLAKY and self._results.get(name) == INCOMPLETE:
      self._set_result(name, INCOMPLETE)
      suite_results.report_update_test(self, name, INCOMPLETE)

  @classmethod
  def _determine_actual_status(cls, status, expect):
    assert status in [EXPECT_PASS, EXPECT_FAIL]
    assert cls._is_valid_expectation(expect)

    if status == EXPECT_PASS:
      if expect in [cls._SHOULD_PASS, cls._MAYBE_FLAKY]:
        return EXPECT_PASS
      elif expect in [cls._SHOULD_FAIL, cls._SHOULD_SKIP]:
        return UNEXPECT_PASS
    elif status == EXPECT_FAIL:
      if expect in [cls._SHOULD_PASS, cls._SHOULD_SKIP]:
        return UNEXPECT_FAIL
      elif expect in [cls._SHOULD_FAIL]:
        return EXPECT_FAIL
      elif expect in [cls._MAYBE_FLAKY]:
        return FLAKE
    return status

  @classmethod
  def _is_valid_expectation(cls, exp):
    return exp in [cls._SHOULD_PASS, cls._SHOULD_FAIL, cls._SHOULD_SKIP,
                   cls._MAYBE_FLAKY]

  def get_expectations(self):
    expectations = {}
    for name, expectation in self._expectations.iteritems():
      expectations[name] = self._MAP_EXPECTATIONS_TO_RESULT[expectation]
    if len(self._expectations) == 0:
      expectations[self.ALL_TESTS_DUMMY_NAME] = (
          self._MAP_EXPECTATIONS_TO_RESULT[self._default_expectation])
    return expectations
