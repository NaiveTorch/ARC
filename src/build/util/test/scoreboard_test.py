#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from collections import Counter
import scoreboard
import suite_results
from suite_runner_config_flags import FAIL
from suite_runner_config_flags import FLAKY
from suite_runner_config_flags import PASS
from suite_runner_config_flags import TIMEOUT
from test_method_result import TestMethodResult


def _noop(*args):
  pass


class TestHelper:
  def __init__(self, name, expect, actual):
    self._name = name
    self._expect = expect
    self._actual = actual

  @property
  def name(self):
    return self._name

  @property
  def expectation(self):
    return self._expect

  @property
  def result(self):
    return self._actual


class ScoreboardTests(unittest.TestCase):
  def setUp(self):
    self._test_counter = Counter()
    self._expected_test_count = 0

    def _report_start(score_board):
      self._test_counter = Counter()

    def _report_update_test(score_board, name, status, duration=0):
      self._test_counter[status] += 1
      # FLAKE causes one more run, so update the expected count.
      if status == scoreboard.FLAKE:
        self._expected_test_count += 1

    def _report_results(score_board):
      self.assertEqual(self._expected_test_count,
                       sum(self._test_counter.values()))

    self.report_start_fn = suite_results.report_start
    self.report_restart_fn = suite_results.report_restart
    self.report_abort_fn = suite_results.report_abort
    self.report_start_test_fn = suite_results.report_start_test
    self.report_update_test_fn = suite_results.report_update_test
    self.report_results_fn = suite_results.report_results
    suite_results.report_start = _report_start
    suite_results.report_results = _report_results
    suite_results.report_abort = _noop
    suite_results.report_start_test = _noop
    suite_results.report_update_test = _report_update_test
    suite_results.report_restart = _noop

  def tearDown(self):
    suite_results.report_start = self.report_start_fn
    suite_results.report_restart = self.report_restart_fn
    suite_results.report_abort = self.report_abort_fn
    suite_results.report_start_test = self.report_start_test_fn
    suite_results.report_update_test = self.report_update_test_fn
    suite_results.report_results = self.report_results_fn

  def _update_tests(self, sb, actuals):
    for name, result in actuals.iteritems():
      sb.start_test(name)
      if result:
        sb.update([TestMethodResult(name, result)])

  def _register_tests(self, sb, tests):
    self._expected_test_count = len(tests)
    sb.register_tests(tests)

  def _check_scoreboard(self, sb, results):
    # The 'default' results for a scoreboard.  Specific results are then
    # overridden by the 'results' parameter.
    results_with_defaults = {
        'overall_status': scoreboard.EXPECT_PASS,
        'total': 0,
        'completed': 0,
        'incompleted': 0,
        'passed': 0,
        'failed': 0,
        'expected_passed': 0,
        'unexpected_passed': 0,
        'expected_failed': 0,
        'unexpected_failed': 0,
        'skipped': 0,
        'restarts': 0,
        'get_flaky_tests': [],
        'get_skipped_tests': [],
        'get_incomplete_tests': [],
        'get_expected_passing_tests': [],
        'get_unexpected_passing_tests': [],
        'get_expected_failing_tests': [],
        'get_unexpected_failing_tests': [],
        'get_incomplete_blacklist': [],
    }
    results_with_defaults.update(results)

    # Go through each result and check it against the scorebord.
    for attribute, expected in results_with_defaults.iteritems():
      actual = getattr(sb, attribute)
      # Some attributes are functions (eg. get_incomplete_blacklist).
      if callable(actual):
        actual = actual()
      self.assertEquals(actual, expected, '%s: %s, expected %s' %
                        (attribute, str(actual), str(expected)))

    # Check some addition stats for consistency.
    self.assertEquals(sb.passed, sb.expected_passed + sb.unexpected_passed)
    self.assertEquals(sb.failed, sb.expected_failed + sb.unexpected_failed)

  # Helper function that creates, registers, runs and finalizes a scoreboard
  # and then checks the resulting stats.
  def _run(self, suite_name, tests, results):
    expectations = dict((t.name, t.expectation) for t in tests)
    register_tests = [t.name for t in tests]
    start_tests = [t.name for t in tests if t.result]
    actuals = dict((t.name, t.result) for t in tests if t.result)

    sb = scoreboard.Scoreboard(suite_name, expectations)
    self._register_tests(sb, register_tests)
    sb.start(start_tests)
    self._update_tests(sb, actuals)
    sb.finalize()
    self._check_scoreboard(sb, results)

  # Setup to run one test and have it pass.
  def test_expected_pass(self):
    tests = [
        TestHelper('test', PASS, TestMethodResult.PASS),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['test'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._run('suite', tests, results)

  # Setup to run one test and have it pass unexpectedly.
  def test_unexpected_pass(self):
    tests = [
        TestHelper('test', FAIL, TestMethodResult.PASS),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'passed': 1,
        'unexpected_passed': 1,
        'get_unexpected_passing_tests': ['test'],
        'overall_status': scoreboard.UNEXPECT_PASS,
    }
    self._run('suite', tests, results)

  # Setup to run one test and have it fail (expectedly).
  def test_expected_fail(self):
    tests = [
        TestHelper('test', FAIL, TestMethodResult.FAIL),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'failed': 1,
        'expected_failed': 1,
        'get_expected_failing_tests': ['test'],
        'overall_status': scoreboard.EXPECT_FAIL,
    }
    self._run('suite', tests, results)

  # Setup to run one test and have it fail.
  def test_unexpected_fail(self):
    tests = [
        TestHelper('test', PASS, TestMethodResult.FAIL),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'failed': 1,
        'unexpected_failed': 1,
        'get_unexpected_failing_tests': ['test'],
        'overall_status': scoreboard.UNEXPECT_FAIL,
    }
    self._run('suite', tests, results)

  # Setup to run one test but do not actually run it.
  def test_skipped(self):
    tests = [
        TestHelper('test', PASS, None),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'skipped': 1,
        'get_skipped_tests': ['test'],
        'overall_status': scoreboard.SKIPPED,
    }
    self._run('suite', tests, results)

  # Setup multiple tests and have them pass, fail, or be skipped.
  def test_all(self):
    tests = [
        TestHelper('pass', PASS, TestMethodResult.PASS),
        TestHelper('fail', PASS, TestMethodResult.FAIL),
        TestHelper('unexpected_passed', FAIL, TestMethodResult.PASS),
        TestHelper('expected_failed', FAIL, TestMethodResult.FAIL),
        TestHelper('skipped', PASS, None),
    ]
    results = {
        'total': 5,
        'completed': 5,
        'passed': 2,
        'failed': 2,
        'expected_passed': 1,
        'unexpected_passed': 1,
        'expected_failed': 1,
        'unexpected_failed': 1,
        'skipped': 1,
        'get_expected_passing_tests': ['pass'],
        'get_unexpected_passing_tests': ['unexpected_passed'],
        'get_expected_failing_tests': ['expected_failed'],
        'get_unexpected_failing_tests': ['fail'],
        'get_skipped_tests': ['skipped'],
        'overall_status': scoreboard.UNEXPECT_FAIL,
    }
    self._run('suite', tests, results)

  # Setup one flaky test and have it pass.
  def test_flake_pass(self):
    tests = [
        TestHelper('flake', FLAKY, TestMethodResult.PASS),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._run('suite', tests, results)

  # Setup one flaky test and have it fail.
  def test_flake_fail(self):
    tests = [
        TestHelper('flake', FLAKY, TestMethodResult.FAIL),
    ]
    results = {
        'total': 1,
        'completed': 1,
        'failed': 1,
        'unexpected_failed': 1,
        'get_unexpected_failing_tests': ['flake'],
        'overall_status': scoreboard.UNEXPECT_FAIL,
    }
    self._run('suite', tests, results)

  # Setup one flaky test, let it fail once, restart, and then have it pass.
  def test_flake_restart_pass(self):
    expectations = {'flake': FLAKY}
    sb = scoreboard.Scoreboard('suite', expectations)

    tests = ['flake']
    self._register_tests(sb, tests)
    sb.start(tests)

    # Fail the test the first time.
    actuals = {'flake': TestMethodResult.FAIL}
    self._update_tests(sb, actuals)
    results = {
        'total': 1,
        'completed': 1,
        'get_flaky_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Restart the tests.
    sb.restart()
    sb.start(tests)

    # Pass the test the second time.
    actuals = {'flake': TestMethodResult.PASS}
    self._update_tests(sb, actuals)
    results = {
        'total': 2,
        'restarts': 1,
        'completed': 2,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Verify finalized results.
    sb.finalize()
    results = {
        'total': 2,
        'restarts': 1,
        'completed': 2,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Note: the number of completed tests cannot be determined by simply
    # adding up the individual results.  This is because flaky tests that
    # failed are neither passing nor failing nor skipped (but they most
    # definitely were completed).
    self.assertNotEqual(sb.completed, sb.passed + sb.failed + sb.skipped)

  # Setup one flaky test, let it not complete.
  def test_flake_incomplete(self):
    expectations = {'flake': FLAKY}
    sb = scoreboard.Scoreboard('suite', expectations)

    tests = ['flake']
    self._register_tests(sb, tests)
    sb.start(tests)

    # The test is never run.
    self.assertEquals(self._test_counter[scoreboard.INCOMPLETE], 0)
    sb.finalize()
    self.assertEquals(self._test_counter[scoreboard.INCOMPLETE], 1)

  # Setup one flaky test, let it fail twice (with a restart between).
  def test_flake_restart_fail(self):
    expectations = {'flake': FLAKY}
    sb = scoreboard.Scoreboard('suite', expectations)

    tests = ['flake']
    self._register_tests(sb, tests)
    sb.start(tests)

    # Fail the test the first time.
    actuals = {'flake': TestMethodResult.FAIL}
    self._update_tests(sb, actuals)
    results = {
        'total': 1,
        'completed': 1,
        'get_flaky_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Restart the tests.
    sb.restart()
    sb.start(tests)

    # Pass the test the second time.
    actuals = {'flake': TestMethodResult.FAIL}
    self._update_tests(sb, actuals)
    results = {
        'total': 2,
        'restarts': 1,
        'completed': 2,
        'get_flaky_tests': ['flake'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Verify finalized results.
    sb.finalize()
    results = {
        'total': 2,
        'completed': 2,
        'failed': 1,
        'restarts': 1,
        'unexpected_failed': 1,
        'get_unexpected_failing_tests': ['flake'],
        'overall_status': scoreboard.UNEXPECT_FAIL,
    }
    self._check_scoreboard(sb, results)

  # Setup three tests, but have one skipped multiple times to have it
  # 'blacklisted'.
  def test_blacklist(self):
    expectations = {
        'alpha': PASS,
        'beta': PASS,
        'gamma': PASS,
    }
    sb = scoreboard.Scoreboard('suite', expectations)
    self._register_tests(sb, ['alpha', 'beta', 'gamma'])

    # Run and pass just the first test.
    sb.start(['alpha', 'beta', 'gamma'])
    actuals = {'alpha': TestMethodResult.PASS}
    self._update_tests(sb, actuals)
    results = {
        'total': 3,
        'completed': 1,
        'incompleted': 2,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['alpha'],
        'get_incomplete_tests': ['beta', 'gamma'],
        'overall_status': scoreboard.INCOMPLETE,
    }
    self._check_scoreboard(sb, results)

    # Restart.
    sb.restart()
    results = {
        'total': 3,
        'restarts': 1,
        'completed': 1,
        'incompleted': 2,
        'passed': 1,
        'expected_passed': 1,
        'get_expected_passing_tests': ['alpha'],
        'get_incomplete_tests': ['beta', 'gamma'],
        'overall_status': scoreboard.INCOMPLETE,
    }
    self._check_scoreboard(sb, results)

    # Run the remaining two tests.
    sb.start(['beta', 'gamma'])
    actuals = {'beta': TestMethodResult.PASS}
    self._update_tests(sb, actuals)
    results = {
        'total': 3,
        'restarts': 1,
        'completed': 2,
        'incompleted': 1,
        'passed': 2,
        'expected_passed': 2,
        'get_expected_passing_tests': ['alpha', 'beta'],
        'get_incomplete_tests': ['gamma'],
        'overall_status': scoreboard.INCOMPLETE,
    }
    self._check_scoreboard(sb, results)

    # After this restart, 'gamma' will have been incomplete twice, so
    # it should get added to the blacklist.
    sb.restart()
    results = {
        'total': 3,
        'restarts': 2,
        'completed': 2,
        'incompleted': 1,
        'passed': 2,
        'expected_passed': 2,
        'get_expected_passing_tests': ['alpha', 'beta'],
        'get_incomplete_tests': ['gamma'],
        'get_incomplete_blacklist': ['gamma'],
        'overall_status': scoreboard.INCOMPLETE,
    }
    self._check_scoreboard(sb, results)

    # Finally run the last test.  Now 'gamma' should no longer be in the
    # blacklist since it ran.
    sb.start(['gamma'])
    actuals = {'gamma': TestMethodResult.PASS}
    self._update_tests(sb, actuals)
    results = {
        'total': 3,
        'completed': 3,
        'passed': 3,
        'expected_passed': 3,
        'restarts': 2,
        'get_expected_passing_tests': ['alpha', 'beta', 'gamma'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

    # Verify all results.
    sb.finalize()
    results = {
        'total': 3,
        'completed': 3,
        'passed': 3,
        'expected_passed': 3,
        'restarts': 2,
        'get_expected_passing_tests': ['alpha', 'beta', 'gamma'],
        'overall_status': scoreboard.EXPECT_PASS,
    }
    self._check_scoreboard(sb, results)

  def test_get_expectations_works_with_named_tests(self):
    sb = scoreboard.Scoreboard(
        'suite', dict(testPasses=PASS, testFails=FAIL, testTimesOut=TIMEOUT,
                      testFlaky=FLAKY))

    expectations = sb.get_expectations()

    self.assertEquals(4, len(expectations))
    self.assertEquals(scoreboard.EXPECT_PASS, expectations['testPasses'])
    self.assertEquals(scoreboard.EXPECT_FAIL, expectations['testFails'])
    self.assertEquals(scoreboard.SKIPPED, expectations['testTimesOut'])
    self.assertEquals(scoreboard.FLAKE, expectations['testFlaky'])

  def test_get_expectations_works_with_dummy_placeholder(self):
    sb = scoreboard.Scoreboard(
        'suite', {scoreboard.Scoreboard.ALL_TESTS_DUMMY_NAME: FAIL})

    expectations = sb.get_expectations()

    self.assertEquals(1, len(expectations))
    self.assertEquals(scoreboard.EXPECT_FAIL,
                      expectations[sb.ALL_TESTS_DUMMY_NAME])
