# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for run_integration_tests

This test runs end-to-end tests of the integration test framework. It does so by
passing in command line arguments to integration_test.main(), and letting all
the internal logic happen, except that all calls to start child processes are
intercepted, and the output specified by the unit tests here is returned.

This allows a typical CTS/ATF style suite run to be simulated, and verifying the
operation of the framework when it encounters various kinds of failures can be
checked.

These tests are meant to verify the functionality of the framework as a whole,
including corner cases in how tests fail and should be retried, as what is
output from rarely used command line options. It is not meant to comprehensively
cover all the logic in the integration test infrastructure.
"""

from mock import patch
import re
import unittest

from build_options import OPTIONS
from run_integration_tests import main
from util.test.suite_runner_config_flags import FLAKY

# TODO(lpique): Unify with similar constants in
# atf_instrumentation_result_parser
ATF_CODE_STARTED = 1
ATF_CODE_PASSED = 0
ATF_CODE_FAILED = -1
ATF_CODE_EXCEPTION = -2
ATF_CODE_FAKE_CRASH = -3  # Note: not a real ATF test code.

# When run on a buildbot, the integration test framework may write out these
# special messages to highlight problems with the build step.
BUILDBOT_STEP_FAILURE_ANNOTATION = '@@@STEP_FAILURE@@@'
BUILDBOT_STEP_WARNINGS_ANNOTATION = '@@@STEP_WARNINGS@@@'

# When run on a buildbot, the integration test framework will retry tests that
# time-out a limited number of times in case the reason for the time-out is
# transitory.
BUILDBOT_TIMEOUT_RETRY_MAX_COUNT = 3

# The summary line can display either using a terse name for each
# count (one/two letters), or as a full word/phrase. If the count is zero,
# the name will not be printed. These are all the statuses, in
# the order they will be printed if nonzero.
SUMMARY_FIELD_NAMES = (('passed', 'P', 'Passed'),
                       ('expected_failed', 'XF', 'Expected Failed'),
                       ('failed', 'F', 'Failed'),
                       ('incomplete', 'I', 'Incomplete'),
                       ('skipped', 'S', 'Skipped'))

# Parses a summary line that is expected to look something like these examples:
#   "1:23 70/70  100%  20 P  50 XF "
#   "1:23 70/70  100%  20 Passed  50 Skipped "
#   "5:02 0/15  100%  15 Incomplete "
# Note that the status counts are optional (only printed if nonzero), but the
# order should be well defined.
SUMMARY_PARSER = re.compile(
    r'\d+:\d+ \d+/\d+\s+\d+% ' +
    ''.join(r'(?: (?P<%s>\d+) %s|%s )?' % field
            for field in SUMMARY_FIELD_NAMES))


class _FakeFilteredSubprocess(object):
  """A fake filtered_subprocess.Popen instance

  When the code under test calls run_process_filtering_output, the
  'output_generator' passed to the constructor will be used to provide fake
  output.
  """
  def __init__(self, output_generator, exit_code):
    self._output_generator = output_generator
    self._exit_code = exit_code

  def run_process_filtering_output(self, handler):
    for line in self._output_generator:
      handler.handle_stdout(line + '\n')

  def wait(self):
    return self._exit_code


class _FakeStream(object):
  """A fake replacement for a stream such as sys.stdout

  Buffers all writes so that they can be examined by calling
  get_output_lines().
  """
  def __init__(self):
    super(_FakeStream, self).__init__()
    self._output = []

  def write(self, text):
    self._output.append(text)

  def fileno(self):
    # We are not a real file, so make any attempt to be treated as one fail.
    return None

  def isatty(self):
    # Returning false here means run_integration_tests will not use ANSI escape
    # codes to colorize the output.
    return False

  def get_output_lines(self):
    # Join and resplit the output into lines.
    return ''.join(self._output).splitlines()


def _make_all_tests_flaky():
  """Helper function for simulating flaky tests

  Altering the expectations for a suite or a test to be flaky is tricky, and
  this helper hides the complexity of doing so.

  It works by intercepting the call to evaluate the suite configuration, and
  substituting a canned configuration in its place that indicates the suite is
  flaky.

  Usage:

      with _make_all_tests_flaky():
          self._run_single_atf_integration_test(...)
  """
  def _make_flaky_suite_configuration(*unused, **kwunused):
    # We must return a new dictionary for every call.
    return dict(
        flags=FLAKY, bug=None, metadata=None, deadline=300, test_order={},
        suite_test_expectations={})
  return patch(
      'util.test.suite_runner_config._SuiteRunConfiguration.evaluate',
      _make_flaky_suite_configuration)


def _make_atf_output_generator(results):
  """Helper function for simulating ATF output

  When a test is run with the `adb shell am instrument` command, it normally
  produces output about the tests that are run, and their status. The
  integration test framework looks for these messages to determine the result of
  each individual test and not just the overall status of the suite. The
  framework uses this information to potentially re-run tests that might be
  flaky, or otherwise retry unusual failures.

  This function generates output, using the 'results' parameter to control what
  results are indicated. Since results is a list, the results of running more
  than one test can be simulated.

  Each entry in the list is expected to be a simple tuple of a string and an
  instrumentation status code. If the status code is ATF_CODE_FAKE_CRASH then
  the output from a crash is simulated.
  """
  for i, (name, status_code) in enumerate(results):
    class_name, test_name = name.split('#', 1)

    yield 'INSTRUMENTATION_STATUS: numtests=%d' % len(results)
    yield 'INSTRUMENTATION_STATUS: test=%s' % test_name
    yield 'INSTRUMENTATION_STATUS: class=%s' % class_name
    yield 'INSTRUMENTATION_STATUS: current=%d' % (1 + i)
    yield 'INSTRUMENTATION_STATUS_CODE: %d' % ATF_CODE_STARTED
    if status_code == ATF_CODE_FAKE_CRASH:
      yield '[  TIMEOUT  ]'
      return
    yield 'INSTRUMENTATION_STATUS: test=%s' % test_name
    yield 'INSTRUMENTATION_STATUS: class=%s' % class_name
    yield 'INSTRUMENTATION_STATUS_CODE: %d' % status_code


def _make_fake_atf_test_process(fake_subprocess_generator):
  """Fakes running an atftest process a number of times.

  This function patches filtered_subprocess.Popen to create fake subprocess
  objects. It examines the call made to Popen to verify that the call appears to
  be one that would launch an atf test run, and then returns the next fake
  subprocess from the _fake_atf_subprocess_generator. This allows for Popen to
  be called multiple times to try/retry each test process.

  Usage:

    with _make_fake_atf_test_process(fake_subprocess_generator):
      # Run code that creates atftest processes.
  """
  # Ensure that we have an iterator interface for the generator.
  fake_subprocess_generator = iter(fake_subprocess_generator)

  def _subprocess_creator(args, *vargs, **kwargs):
    # Make a quick check that we were called with "./launch_chrome atftest"
    if ('launch_chrome' in args and 'atftest' in args):
      # Create and return a mock object that yields the next simulated output.
      return fake_subprocess_generator.next()

    _stub_unexpected_popen(args, *vargs, **kwargs)

  return patch('filtered_subprocess.Popen', _subprocess_creator)


def _stub_return_empty_string(*args, **kwargs):
  """Just returns the empty string for any call."""
  return ''


def _stub_return_none(*args, **kwargs):
  """Just returns None for any call."""
  return None


def _stub_unexpected_popen(args, *vargs, **kwargs):
  """A helper function for trapping calls to launch a subprocess"""
  assert False, 'Unexpected call to launch a subprocess: %s' % args


def _stub_parse_configure_file():
  """A helper function for trapping calls to read the build options file.

  Populate them with the default build configuration instead, so this test
  behaves the same regardless of the actual configuration.
  """
  OPTIONS.parse([])


# These patch decorators replace the named function with a stub/fake/mock for
# each test in the suite.
# Any call to create a general subprocess object will be caught as unexpected.
@patch('filtered_subprocess.Popen', _stub_unexpected_popen)
@patch('subprocess.Popen', _stub_unexpected_popen)
# Any call to subprocess.check_call will just return None.
@patch('subprocess.check_call', _stub_return_none)
# Any call to subprocess.check_output will just return an empty string.
@patch('subprocess.check_output', _stub_return_empty_string)
# We patch sys.stdout.write to hide all output.
@patch('sys.stdout', _FakeStream())
# We stub out build_crx and update_shell_command to do nothing.
# TODO(lpique): Look into making them work without stubbing them out.
@patch('apk_to_crx.build_crx', _stub_return_none)
@patch('prep_launch_chrome.update_shell_command', _stub_return_none)
@patch('build_options.OPTIONS.parse_configure_file', _stub_parse_configure_file)
class RunIntegrationTestsTest(unittest.TestCase):
  # A chosen real test suite, and a test in it. The test should normally pass.
  EXAMPLE_SUITE_NAME = 'cts.android.core.tests.libcore.package.libcore'
  EXAMPLE_TEST_NAME = 'libcore.java.util.TimeZoneTest#testDisplayNames'

  def _run_integration_tests(self, args):
    with patch('sys.stdout', _FakeStream()) as stdout:
      self._last_exit_code = main(args + ['--noninja'])
      self._last_output = stdout.get_output_lines()

  @classmethod
  def _fake_atf_subprocess_generator(cls, result_codes):
    for result_code in result_codes:
      yield _FakeFilteredSubprocess(
          _make_atf_output_generator([(cls.EXAMPLE_TEST_NAME, result_code)]),
          (0 if result_code == ATF_CODE_PASSED else 1))

  def _run_single_atf_integration_test(self, result_codes, extra_args=None):
    """Simulates running the integration test framework on one specific test.

    extra_args are any extra arguments to pass to run_integration_tests.main()
    result_codes is list (or generator) of result codes for each run that can
    occur, and should be one of ATF_CODE_PASSED, ATF_CODE_FAILED,
    ATF_CODE_EXCEPTION, or ATF_CODE_FAKE_CRASH.
    Note that depending on how the test and the framework is configured, a test
    which does not pass may be retried, for example if a test is marked as being
    flaky.
    The result
    """

    # Intercept calls to filtered_subprocess so we can simulate the test.
    with _make_fake_atf_test_process(
        self._fake_atf_subprocess_generator(result_codes)):
      args = ['-t', self.EXAMPLE_SUITE_NAME + ':' + self.EXAMPLE_TEST_NAME]
      if extra_args:
        args.extend(extra_args)

      self._run_integration_tests(args)

  def assertExitCodeIndicatedSuccess(self):
    self.assertEqual(0, self._last_exit_code)

  def assertExitCodeIndicatedFailure(self):
    self.assertNotEqual(0, self._last_exit_code)

  def _get_output_summary(self):
    """Locates and parses the single-line test summary message.

    Returns a dictionary with the counts of tests for each named count.
    Keys for the dictionary are: 'passed', 'expected_failed', 'failed',
    'incomplete', 'skipped'. If no count was output for a given key, the value
    associated with that key will be None.

    For example if the output summary was "01:12 4/128 10%  2 P  6 S ", the
    returned dictionary would be {'passed': 2, 'expected_failed': None,
    'failed': None, 'incomplete': None, 'skipped': 6}.
    """
    # Search from the end since the summary should be one of the last things
    # printed.
    for line in reversed(self._last_output):
      # Try to match on this line.
      m = SUMMARY_PARSER.match(line)
      if m is not None:
        return m.groupdict()
    assert False, ('The expected test run summary was not found in the '
                   'output:\n%s' % '\n'.join(self._last_output))
    return None

  def assertOutputSummaryIndicatesSuccess(self):
    summary = self._get_output_summary()
    self.assertGreater(summary['passed'], 0)
    self.assertIs(summary['failed'], None)
    self.assertIs(summary['incomplete'], None)

  def assertOutputSummaryIndicatesFailure(self):
    summary = self._get_output_summary()
    self.assertGreater(summary['failed'], 0)
    self.assertIs(summary['incomplete'], None)

  def assertOutputSummaryIndicatesIncomplete(self):
    summary = self._get_output_summary()
    self.assertGreater(summary['incomplete'], 0)

  def assertOutputDoesNotContainBuildbotFailureAnnotaion(self):
    self.assertTrue(BUILDBOT_STEP_FAILURE_ANNOTATION not in self._last_output)

  def assertOutputContainsBuildbotFailureAnnotaion(self):
    self.assertTrue(BUILDBOT_STEP_FAILURE_ANNOTATION in self._last_output)

  def assertOutputDoesNotContainBuildbotWarningAnnotaion(self):
    self.assertTrue(BUILDBOT_STEP_WARNINGS_ANNOTATION not in self._last_output)

  def assertOutputContainsBuildbotWarningAnnotaion(self):
    self.assertTrue(BUILDBOT_STEP_WARNINGS_ANNOTATION in self._last_output)

  def assertSingleTestSuccess(self):
    self.assertExitCodeIndicatedSuccess()
    self.assertOutputSummaryIndicatesSuccess()

  def assertSingleTestFailure(self):
    self.assertExitCodeIndicatedFailure()
    self.assertOutputSummaryIndicatesFailure()

  def assertSingleTestIncomplete(self):
    self.assertExitCodeIndicatedFailure()
    self.assertOutputSummaryIndicatesIncomplete()

  def assertSingleTestSuccessBuildbot(self):
    self.assertExitCodeIndicatedSuccess()
    self.assertOutputSummaryIndicatesSuccess()
    self.assertOutputDoesNotContainBuildbotFailureAnnotaion()

  def assertSingleTestFailureBuildbot(self):
    self.assertExitCodeIndicatedFailure()
    self.assertOutputSummaryIndicatesFailure()
    self.assertOutputContainsBuildbotFailureAnnotaion()

  def assertSingleTestIncompleteBuildbot(self):
    self.assertExitCodeIndicatedFailure()
    self.assertOutputSummaryIndicatesIncomplete()
    self.assertOutputContainsBuildbotFailureAnnotaion()

  def test_single_test_passing(self):
    """A single test that cleanly passes should output as success."""
    self._run_single_atf_integration_test([ATF_CODE_PASSED])
    self.assertSingleTestSuccess()

  def test_single_test_failing(self):
    """A single test that cleanly passes should output as failure."""
    self._run_single_atf_integration_test([ATF_CODE_FAILED])
    self.assertSingleTestFailure()

  def test_single_test_aborting(self):
    """A single test that cleanly aborts should output as failure."""
    self._run_single_atf_integration_test([ATF_CODE_EXCEPTION])
    self.assertSingleTestFailure()

  def test_single_test_incomplete(self):
    """A single test that crashes should output as incomplete."""
    self._run_single_atf_integration_test([ATF_CODE_FAKE_CRASH])
    self.assertSingleTestIncomplete()

  def test_single_test_flake(self):
    """A flaky test should be retried."""
    with _make_all_tests_flaky():
      self._run_single_atf_integration_test(
          [ATF_CODE_FAILED, ATF_CODE_PASSED])
    self.assertSingleTestSuccess()

  def test_single_test_first_run_incomplete_on_buildbot(self):
    """A test that crashes should be retried on a buildbot."""
    self._run_single_atf_integration_test(
        [ATF_CODE_FAKE_CRASH, ATF_CODE_PASSED],
        extra_args=['--buildbot'])
    self.assertSingleTestSuccessBuildbot()

  def test_can_pass_after_not_completing_at_the_retry_limit_on_buildbot(self):
    """A test that crashes should be retried on a buildbot up to a limit."""
    self._run_single_atf_integration_test(
        ([ATF_CODE_FAKE_CRASH] * (BUILDBOT_TIMEOUT_RETRY_MAX_COUNT - 1) +
         [ATF_CODE_PASSED]),
        extra_args=['--buildbot'])
    self.assertSingleTestSuccessBuildbot()

  def test_if_does_not_complete_enough_counts_as_incomplete_on_buildbot(self):
    """A test that crashes too many times on a buildbot counts as failure."""
    self._run_single_atf_integration_test(
        [ATF_CODE_FAKE_CRASH] * BUILDBOT_TIMEOUT_RETRY_MAX_COUNT,
        extra_args=['--buildbot'])
    self.assertSingleTestIncompleteBuildbot()

  def test_incomplete_flaky_tests_counts_as_incomplete_on_buildbot(self):
    """A flaky test that crashes too many times on a buildbot counts as
    incomplete."""
    with _make_all_tests_flaky():
      self._run_single_atf_integration_test(
          [ATF_CODE_FAKE_CRASH] * BUILDBOT_TIMEOUT_RETRY_MAX_COUNT,
          extra_args=['--buildbot'])
    self.assertSingleTestIncompleteBuildbot()

  def test_single_test_flake_on_buildbot(self):
    """A flaky test should be retried on a buildbot."""
    with _make_all_tests_flaky():
      self._run_single_atf_integration_test(
          [ATF_CODE_FAILED, ATF_CODE_PASSED],
          extra_args=['--buildbot'])
    self.assertSingleTestSuccessBuildbot()

  def test_single_test_passing_on_buildbot(self):
    """A single test that cleanly passes on a buildbot count as success."""
    self._run_single_atf_integration_test(
        [ATF_CODE_PASSED],
        extra_args=['--buildbot'])
    self.assertSingleTestSuccessBuildbot()

  def test_single_test_failing_on_buildbot(self):
    """A single test that cleanly fails on a buildbot count as failure."""
    self._run_single_atf_integration_test(
        [ATF_CODE_FAILED],
        extra_args=['--buildbot'])
    self.assertSingleTestFailureBuildbot()

  def test_single_test_passing_as_cts_buildbot(self):
    """A single test that cleanly failes on a CTS buildbot count as success."""
    self._run_single_atf_integration_test(
        [ATF_CODE_PASSED],
        extra_args=['--buildbot', '--cts-bot'])

    # A failure on the CTS bot should be treated normally.
    self.assertSingleTestSuccessBuildbot()
    self.assertOutputDoesNotContainBuildbotWarningAnnotaion()

  def test_single_test_failing_as_cts_buildbot(self):
    """A single test that cleanly failes on a CTS buildbot count as warning."""
    self._run_single_atf_integration_test(
        [ATF_CODE_FAILED],
        extra_args=['--buildbot', '--cts-bot'])

    # A failure on the CTS bot should not fail the build.
    self.assertExitCodeIndicatedSuccess()
    self.assertOutputDoesNotContainBuildbotFailureAnnotaion()
    self.assertOutputContainsBuildbotWarningAnnotaion()

  def test_plan_report_can_be_printed_for_all_suites(self):
    """Check that the --plan-report option appears to work."""
    self._run_integration_tests(['-t', '*', '--plan-report'])
    self.assertExitCodeIndicatedSuccess()
    self.assertTrue(
        any(line.endswith(self.EXAMPLE_SUITE_NAME)
            for line in self._last_output),
        'Did not find a line ending with "%s" in %s' % (
            self.EXAMPLE_SUITE_NAME, self._last_output))

  def test_list_can_be_generated_for_all_suites(self):
    """Check that --list can be used to list all tests."""
    self._run_integration_tests(['-t', '*', '--list'])
    self.assertExitCodeIndicatedSuccess()
    self.assertIn(self.EXAMPLE_SUITE_NAME + ':' + self.EXAMPLE_TEST_NAME,
                  self._last_output)

  def test_list_is_blank_if_no_tests_selected(self):
    """Check that --list works with no tests selected."""
    self._run_integration_tests(['-t', 'should-match-nothing', '--list'])
    self.assertExitCodeIndicatedSuccess()
    self.assertEquals([], self._last_output)

  def test_simple_select_of_all_tests_in_suite(self):
    """Check that --list works when selecting all tests in a suite."""
    self._run_integration_tests(['-t', self.EXAMPLE_SUITE_NAME, '--list'])
    self.assertExitCodeIndicatedSuccess()
    self.assertIn(self.EXAMPLE_SUITE_NAME + ':' + self.EXAMPLE_TEST_NAME,
                  self._last_output)

  def test_simple_select_of_one_test_in_suite(self):
    """Check that --list works when selecting a single test in a suite."""
    self._run_integration_tests([
        '-t', self.EXAMPLE_SUITE_NAME + ':' + self.EXAMPLE_TEST_NAME,
        '--list'])
    self.assertExitCodeIndicatedSuccess()
    self.assertIn(self.EXAMPLE_SUITE_NAME + ':' + self.EXAMPLE_TEST_NAME,
                  self._last_output)

if __name__ == '__main__':
  unittest.main()
