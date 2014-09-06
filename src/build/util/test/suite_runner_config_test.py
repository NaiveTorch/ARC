#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import unittest

from util.test.scoreboard import Scoreboard
from util.test.suite_runner import SuiteRunnerBase
from util.test.suite_runner_config import _SuiteRunConfiguration
from util.test.suite_runner_config import DEFAULT_OUTPUT_TIMEOUT
from util.test.suite_runner_config import make_suite_run_configs
from util.test.suite_runner_config import SUITE_DEFAULTS
from util.test.suite_runner_config_flags import _ExclusiveFlag
from util.test.suite_runner_config_flags import ExclusiveFlagSet
from util.test.suite_runner_config_flags import FAIL
from util.test.suite_runner_config_flags import FLAKY
from util.test.suite_runner_config_flags import LARGE
from util.test.suite_runner_config_flags import NOT_SUPPORTED
from util.test.suite_runner_config_flags import PASS
from util.test.suite_runner_config_flags import REQUIRES_OPENGL
from util.test.suite_runner_config_flags import TIMEOUT
from util.test.test_options import TEST_OPTIONS


def _set_default_flag_settings():
  TIMEOUT.set_should_include_by_default(False)
  LARGE.set_should_include_by_default(False)
  NOT_SUPPORTED.set_should_not_run(True)
  REQUIRES_OPENGL.set_should_not_run(False)


def ones_count(x):
  """Returns the count of 1 bits in the input."""
  return bin(x).count("1")  # More efficient than a python loop.


class SuiteFlagMergeTest(unittest.TestCase):
  def test_pass_exclusive_with_fail(self):
    # These all should have the same mask to be properly exclusive.
    self.assertEquals(PASS._mask, FAIL._mask)
    self.assertEquals(PASS._mask, NOT_SUPPORTED._mask)
    self.assertEquals(PASS._mask, TIMEOUT._mask)

    # Verify that merging FAIL clears PASS, and visa-versa.
    flags = PASS
    self.assertIn(PASS, flags)
    self.assertNotIn(FAIL, flags)
    flags |= FAIL
    self.assertIn(FAIL, flags)
    self.assertNotIn(PASS, flags)
    flags |= PASS
    self.assertIn(PASS, flags)
    self.assertNotIn(FAIL, flags)

  def test_complex_merge(self):
    flags = PASS
    self.assertIsInstance(flags, _ExclusiveFlag)
    self.assertIn(PASS, flags)
    self.assertNotIn(FLAKY, flags)
    self.assertNotIn(LARGE, flags)
    self.assertNotIn(REQUIRES_OPENGL, flags)
    self.assertEquals(1, ones_count(flags._value))
    self.assertEquals(PASS._mask, flags._mask)

    flags |= FLAKY
    self.assertIsInstance(flags, ExclusiveFlagSet)
    self.assertIn(PASS, flags)
    self.assertIn(FLAKY, flags)
    self.assertNotIn(LARGE, flags)
    self.assertNotIn(REQUIRES_OPENGL, flags)
    self.assertEquals(2, ones_count(flags._value))
    self.assertEquals(PASS._mask, flags._mask)

    temp = LARGE | REQUIRES_OPENGL
    self.assertIsInstance(temp, ExclusiveFlagSet)
    self.assertNotIn(PASS, temp)
    self.assertNotIn(FLAKY, temp)
    self.assertIn(LARGE, temp)
    self.assertIn(REQUIRES_OPENGL, temp)
    self.assertEquals(2, ones_count(temp._value))
    self.assertEquals(0, temp._mask)

    flags |= temp
    self.assertIsInstance(flags, ExclusiveFlagSet)
    self.assertIn(PASS, flags)
    self.assertIn(FLAKY, flags)
    self.assertIn(LARGE, flags)
    self.assertIn(REQUIRES_OPENGL, flags)
    self.assertEquals(4, ones_count(flags._value))
    self.assertEquals(PASS._mask, flags._mask)


class SuiteRunConfigInputTests(unittest.TestCase):
  """Tests the evaluation of the input configuration."""

  @staticmethod
  def _evaluate(name, configuration, defaults=None):
    c = _SuiteRunConfiguration(name, configuration)
    c.validate()
    return c.evaluate(defaults=defaults)

  def test_defaults_applied(self):
    result = self._evaluate('simple', dict(flags=PASS),
                            defaults=dict(bug=1234, flags=FAIL))
    self.assertEquals(1234, result['bug'])
    self.assertEquals(DEFAULT_OUTPUT_TIMEOUT, result['deadline'])
    self.assertIn(PASS, result['flags'])
    self.assertNotIn(FAIL, result['flags'])

  def test_simple_passing_test(self):
    self.assertIn(PASS, self._evaluate('simple', None)['flags'])
    self.assertIn(PASS, self._evaluate('simple', {})['flags'])
    self.assertIn(PASS, self._evaluate('simple', dict(flags=PASS))['flags'])

  def test_simple_failing_test(self):
    result = self._evaluate('simple', dict(flags=FAIL))
    self.assertNotIn(PASS, result['flags'])
    self.assertIn(FAIL, result['flags'])

  def test_configured_to_fail_for_target(self):
    result = self._evaluate('', dict(configurations=[
        dict(flags=FAIL | FLAKY)]))
    self.assertNotIn(PASS, result['flags'])
    self.assertIn(FAIL, result['flags'])
    self.assertIn(FLAKY, result['flags'])

    result = self._evaluate('', dict(configurations=[
        dict(enable_if=False, flags=FAIL | FLAKY)]))
    self.assertIn(PASS, result['flags'])
    self.assertNotIn(FAIL, result['flags'])
    self.assertNotIn(FLAKY, result['flags'])

  def test_suite_test_expectations(self):
    result = self._evaluate('simple', dict(suite_test_expectations=dict(
        foo=dict(bar=FLAKY))))
    expectations = result['suite_test_expectations']
    self.assertIn(PASS, expectations['foo#bar'])
    self.assertIn(FLAKY, expectations['foo#bar'])
    self.assertNotIn(FAIL, expectations['foo#bar'])
    self.assertNotIn(NOT_SUPPORTED, expectations['foo#bar'])

  def test_suite_test_order(self):
    result = self._evaluate('simple', dict(configurations=[
        dict(test_order=collections.OrderedDict(foo=1))]))
    test_order = result['test_order']
    self.assertIn('foo', test_order)
    self.assertEquals(test_order['foo'], 1)


class SuiteRunConfigIntegrationTests(unittest.TestCase):
  """Uses the module interface as intended."""

  # This is the configuration the tests will use:
  my_config = staticmethod(make_suite_run_configs(lambda: {
      SUITE_DEFAULTS: {
          'flags': PASS,
          'deadline': 60,
      },
      'dummy_suite_1': None,
      'dummy_suite_2': {},
      'dummy_suite_3': {
          'flags': FAIL,
          'bug': 'crbug.com/123123',
      },
      'dummy_suite_4': {
          'flags': LARGE,
          'configurations': [{
              'test_order': collections.OrderedDict([
                  ('priMethod', -1)]),
              'suite_test_expectations': {
                  'Class1': {
                      'method1': FAIL,
                      'method2': FLAKY,
                  },
                  'test3': TIMEOUT,
              },
          }],
      },
  }))

  def setUp(self):
    _set_default_flag_settings()
    TEST_OPTIONS.reset()

  def _make_suite_runner(self, name):
    options = SuiteRunConfigIntegrationTests.my_config()[name]
    return SuiteRunnerBase(name, **options)

  def test_works_as_intended(self):
    runner = self._make_suite_runner('dummy_suite_1')
    self.assertEquals(PASS, runner.suite_expectation)
    self.assertEquals({Scoreboard.ALL_TESTS_DUMMY_NAME: PASS},
                      runner.suite_test_expectations)
    self.assertEquals(60, runner.deadline)
    self.assertEquals(None, runner.bug)

    runner = self._make_suite_runner('dummy_suite_2')
    self.assertEquals(PASS, runner.suite_expectation)
    self.assertEquals({Scoreboard.ALL_TESTS_DUMMY_NAME: PASS},
                      runner.suite_test_expectations)
    self.assertEquals(60, runner.deadline)
    self.assertEquals(None, runner.bug)

    runner = self._make_suite_runner('dummy_suite_3')
    self.assertEquals(FAIL, runner.suite_expectation)
    self.assertEquals({Scoreboard.ALL_TESTS_DUMMY_NAME: FAIL},
                      runner.suite_test_expectations)
    self.assertEquals(60, runner.deadline)
    self.assertEquals('crbug.com/123123', runner.bug)

    runner = self._make_suite_runner('dummy_suite_4')
    self.assertEquals(LARGE | PASS, runner.suite_expectation)
    self.assertEquals(3, len(runner.suite_test_expectations))
    self.assertIn(FAIL, runner.suite_test_expectations['Class1#method1'])
    self.assertIn(LARGE, runner.suite_test_expectations['Class1#method1'])
    self.assertIn(PASS, runner.suite_test_expectations['Class1#method2'])
    self.assertIn(FLAKY, runner.suite_test_expectations['Class1#method2'])
    self.assertIn(LARGE, runner.suite_test_expectations['Class1#method2'])
    self.assertIn(TIMEOUT, runner.suite_test_expectations['test3'])
    self.assertEquals(60, runner.deadline)
    self.assertEquals(None, runner.bug)
    self.assertEquals(
        ['priMethod', 'abcMethod', 'xyzMethod'],
        runner.apply_test_ordering(['xyzMethod', 'abcMethod', 'priMethod']))
