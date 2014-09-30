#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs all Android integration tests/suites.

Dynamically loads all the config.py files in the source code directories,
specifically looking for ones that define a function:

    def get_integration_test_runners():
      return [...]

Each such function is expected to return a list of test runner objects which
extend SuiteRunnerBase or one of its subclasses to implement the logic for
running that test suite.
"""

import argparse
import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
from fnmatch import fnmatch

import build_common
import config_loader
import dashboard_submit
import util.test.suite_results
from build_options import OPTIONS
from cts import expected_driver_times
from cts import generate_cts_runners
from util import color
from util import concurrent
from util import debug
from util import platform_util
from util import remote_executor
from util.test import scoreboard_constants
from util.test import test_driver
from util.test.suite_results import report_expected_results
from util.test.suite_runner import SuiteRunnerBase
from util.test.suite_runner_config_flags import FAIL
from util.test.suite_runner_config_flags import LARGE
from util.test.suite_runner_config_flags import NOT_SUPPORTED
from util.test.suite_runner_config_flags import REQUIRES_OPENGL
from util.test.suite_runner_config_flags import TIMEOUT
from util.test.test_options import TEST_OPTIONS


BOT_TEST_SUITE_MAX_RETRY_COUNT = 5
TEST_METHOD_MAX_RETRY_COUNT = 5


_REPORT_COLOR_FOR_SUITE_EXPECTATION = {
    scoreboard_constants.SKIPPED: color.MAGENTA,
    scoreboard_constants.EXPECT_FAIL: color.RED,
    scoreboard_constants.FLAKE: color.CYAN,
    scoreboard_constants.EXPECT_PASS: color.GREEN,
}


def _get_all_suite_runners():
  """Gets all the suites defined in the various config.py files."""
  all_suite_runners = []
  used_names = set()

  # Look for config.py modules that define 'get_integration_test_runners',
  # and call it to get a list of test runner objects we can use to identify
  # and run each test.
  get_runners_list = list(
      config_loader.find_name('get_integration_test_runners'))
  get_runners_list.append(generate_cts_runners.get_integration_test_runners)

  for get_runners in get_runners_list:
    for suite_runner in get_runners():
      assert suite_runner.name not in used_names, (
          'Test case "%s" is multiply defined.' % suite_runner.name)
      used_names.add(suite_runner.name)
      all_suite_runners.append(suite_runner)

  return sorted(all_suite_runners, key=lambda suite_runner: suite_runner.name)


def get_configs_for_integration_tests():
  """Gets the paths of config.py that are needed to run integration tests."""
  configs = []
  # All config files that define 'get_integration_test_runners' are needed to
  # run integration tests.
  for config_module in config_loader.find_config_modules(
      'get_integration_test_runners'):
    config_file = os.path.relpath(config_module.__file__,
                                  build_common.get_arc_root())
    # config_file can be '*.pyc'. In this case, use the corresponding .py file.
    root, ext = os.path.splitext(config_file)
    if ext == '.pyc':
      config_file = root + '.py'
    configs.append(config_file)
  # These do not define get_integration_test_runners but used by other scripts.
  configs.extend(['mods/android/external/stlport/config.py',
                  'src/posix_translation/config.py'])
  return configs


def _should_include_test_method(name, expectation, args):
  if not args.include_patterns:
    result = expectation.should_include_by_default
  else:
    result = any(fnmatch(name, pattern)
                 for pattern in args.include_patterns)

  return result and all(not fnmatch(name, pattern)
                        for pattern in args.exclude_patterns)


def _select_tests_to_run(all_suite_runners, args):
  test_driver_list = []
  for suite_runner in all_suite_runners:
    # Form a list of selected tests for this suite, by forming a fully qualified
    # name as "<suite-name>:<test-name>", which is what the patterns given on
    # as command line arguments expect to match.
    tests_to_run = []
    updated_suite_test_expectations = {}
    do_not_run_suite = not suite_runner.check_test_runnable()
    suite_test_expectations = suite_runner.suite_test_expectations
    for test_name, test_expectation in suite_test_expectations.iteritems():
      # Check if the test is selected.
      fqn = '%s:%s' % (suite_runner.name, test_name)
      if not _should_include_test_method(fqn, test_expectation, args):
        continue

      # Add this test and its updated expectation to the dictionary of all
      # selected tests. We do this even if just below we do not decide we can
      # actually run the test, as otherwise we do not know if it was skipped or
      # not.
      updated_suite_test_expectations[test_name] = test_expectation

      # Exclude tests either because the suite is not runnable, or because each
      # individual test is not runnable.
      if do_not_run_suite or test_expectation.should_not_run:
        continue

      tests_to_run.append(test_name)

    # If no tests from this suite were selected, continue with the next suite.
    if not updated_suite_test_expectations:
      continue

    # Create TestDriver to run the test suite with setting test expectations.
    test_driver_list.append(test_driver.TestDriver(
        suite_runner, updated_suite_test_expectations, tests_to_run,
        TEST_METHOD_MAX_RETRY_COUNT if not args.keep_running else sys.maxint,
        stop_on_unexpected_failures=not args.keep_running))

  def sort_keys(driver):
    # Take the negative time to sort descending, while otherwise sorting by name
    # ascending.
    return (-expected_driver_times.get_expected_driver_time(driver),
            driver.name)

  return sorted(test_driver_list, key=sort_keys)


def _get_test_driver_list(args):
  all_suite_runners = _get_all_suite_runners()
  return _select_tests_to_run(all_suite_runners, args)


def _run_driver(driver, args, prepare_only):
  """Runs a single suite."""
  try:
    # TODO(mazda): Move preparation into its own parallel pass.  It's confusing
    # running during something called "run_single_suite".
    if not args.noprepare:
      driver.prepare(args)

    # Run the suite locally when not being invoked for remote execution.
    if not prepare_only:
      driver.run(args)

  finally:
    driver.finalize(args)


def _shutdown_unfinished_drivers_gracefully(not_done, test_driver_list):
  """Kills unfinished concurrent test drivers as gracefully as possible."""
  # Prevent new tasks from running.
  not_cancelled = []
  for future in not_done:
    # Note: Running tasks cannot be cancelled.
    if not future.cancel():
      not_cancelled.append(future)

  # We try to terminate first, as ./launch_chrome will respond by shutting
  # down the chrome process cleanly. The later kill() call will not do so,
  # and could leave a running process behind. At this point, consider any
  # tests that have not finished as incomplete.
  for driver in test_driver_list:
    driver.terminate()

  # Give everyone ten seconds to terminate.
  _, not_cancelled = concurrent.wait(not_cancelled, 10)
  if not not_cancelled:
    return

  # There still remain some running tasks. Kill them.
  for driver in test_driver_list:
    driver.kill()
  concurrent.wait(not_cancelled, 5)


def _run_suites(test_driver_list, args, prepare_only=False):
  """Runs the indicated suites."""
  _prepare_output_directory(args)

  util.test.suite_results.initialize(test_driver_list, args, args.remote)

  if not test_driver_list:
    return False

  timeout = (
      args.total_timeout if args.total_timeout and not prepare_only else None)

  try:
    with concurrent.ThreadPoolExecutor(args.jobs, daemon=True) as executor:
      futures = [executor.submit(_run_driver, driver, args, prepare_only)
                 for driver in test_driver_list]
      done, not_done = concurrent.wait(futures, timeout,
                                       concurrent.FIRST_EXCEPTION)
      try:
        # Iterate over the results to propagate an exception if any of the tasks
        # aborted by an error in the test drivers. Since such an error is due to
        # broken script rather than normal failure in tests, we prefer just to
        # die similarly as when Python errors occurred in the main thread.
        for future in done:
          future.result()

        # No exception was raised but some timed-out tasks are remaining.
        if not_done:
          print '@@@STEP_TEXT@Integration test timed out@@@'
          debug.write_frames(sys.stdout)
          print '@@@STEP_FAILURE@@@'
          return False

        # All tests passed (or failed) in time.
        return True
      finally:
        if not_done:
          _shutdown_unfinished_drivers_gracefully(not_done, test_driver_list)
  finally:
    for driver in test_driver_list:
      driver.finalize(args)


def prepare_suites(args):
  test_driver_list = _get_test_driver_list(args)
  if not test_driver_list:
    # unittest.* run only on Chrome OS and if they are selected with -t,
    # test_driver_list becomes empty. That is OK.
    return True
  return _run_suites(test_driver_list, args, prepare_only=True)


def list_fully_qualified_test_names(scoreboards, args):
  output = []
  for scoreboard in scoreboards:
    suite_name = scoreboard.name
    for test_name, expectation in scoreboard.get_expectations().iteritems():
      output.append(('%s:%s' % (suite_name, test_name), expectation))
  output.sort()
  for fqn, expectation in output:
    color.write_ansi_escape(
        sys.stdout, _REPORT_COLOR_FOR_SUITE_EXPECTATION[expectation],
        fqn + '\n')


def print_chrome_version():
  assert not platform_util.is_running_on_cygwin(), (
      'Chrome on Windows does not support --version option.')
  chrome_path = remote_executor.get_chrome_exe_path()
  chrome_version = subprocess.check_output([chrome_path, '--version']).rstrip()
  print '@@@STEP_TEXT@%s<br/>@@@' % (chrome_version)


def parse_args(args):
  description = 'Runs integration tests, verifying they pass.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('--buildbot', action='store_true', help='Run tests '
                      'for the buildbot.')
  parser.add_argument('--cts-bot', action='store_true',
                      help='Run with CTS bot specific config.')
  parser.add_argument('--enable-osmesa', action='store_true',
                      help=('This flag wlll be passed to launch_chome '
                            'to control GL emulation with OSMesa.'))
  parser.add_argument('--include-failing', action='store_true',
                      help='Include tests which are expected to fail.')
  parser.add_argument('--include-large', action='store_true',
                      help=('Include large tests that may take a long time to '
                            'run.'))
  parser.add_argument('--include-timeouts', action='store_true',
                      help='Include tests which are expected to timeout.')
  parser.add_argument('-j', '--jobs', metavar='N', type=int,
                      default=min(10, multiprocessing.cpu_count() + 1),
                      help='Run N tests at once.')
  parser.add_argument('--keep-running', action='store_true',
                      help=('Attempt to recover from unclean failures. '
                            'Sacrifices failing quickly for complete results. '
                            ''))
  parser.add_argument('--launch-chrome-opt', action='append', default=[],
                      dest='launch_chrome_opts', metavar='OPTIONS',
                      help=('An Option to pass on to launch_chrome. Repeat as '
                            'needed for any options to pass on.'))
  parser.add_argument('--list', action='store_true',
                      help=('List the fully qualified names of tests. '
                            'Can be used with -t and --include-* flags.'))
  parser.add_argument('--max-deadline', '--max-timeout',
                      metavar='T', default=0, type=int,
                      help=('Maximum deadline for browser tests. The test '
                            'configuration deadlines are used by default.'))
  parser.add_argument('--min-deadline', '--min-timeout',
                      metavar='T', default=0, type=int,
                      help=('Minimum deadline for browser tests. The test '
                            'configuration deadlines are used by default.'))
  parser.add_argument('--noninja', action='store_false',
                      default=True, dest='run_ninja',
                      help='Do not run ninja before running any tests.')
  parser.add_argument('--noprepare', action='store_true',
                      help='Do not run the suite prepare step - useful for '
                           'running integration tests from an archived test '
                           'bundle.')
  parser.add_argument('-o', '--output-dir', metavar='DIR',
                      help='Specify the directory to store test ouput files.')
  parser.add_argument('--plan-report', action='store_true',
                      help=('Generate a report of all tests based on their '
                            'currently configured expectation of success.'))
  parser.add_argument('-q', '--quiet', action='store_true',
                      help='Do not show passing tests and expected failures.')
  parser.add_argument('--stop', action='store_true',
                      help=('Stops running tests immediately when a failure '
                            'is reported.'))
  parser.add_argument('-t', '--include', action='append',
                      dest='include_patterns', default=[], metavar='PATTERN',
                      help=('Identifies tests to include, using shell '
                            'style glob patterns. For example dalvik.*'))
  parser.add_argument('--times', metavar='N',
                      default=1, type=int, dest='repeat_runs',
                      help='Runs each test N times.')
  parser.add_argument('--total-timeout', metavar='T', default=0, type=int,
                      help=('If specified, this script stops after running '
                            'this seconds.'))
  parser.add_argument('--use-xvfb', action='store_true', help='Use xvfb-run'
                      'when launching tests.  Used by buildbots.')
  parser.add_argument('-v', '--verbose', action='store_const', const='verbose',
                      dest='output', help='Verbose output.')
  parser.add_argument('-x', '--exclude', action='append',
                      dest='exclude_patterns', default=[], metavar='PATTERN',
                      help=('Identifies tests to exclude, using shell '
                            'style glob patterns. For example dalvik.tests.*'))

  remote_executor.add_remote_arguments(parser)

  return parser.parse_args(args)


def set_test_options(args):
  TEST_OPTIONS.set_is_running_on_buildbot(args.buildbot)
  TEST_OPTIONS.set_supports_opengl(OPTIONS.is_hw_renderer() and
                                   not args.use_xvfb)
  TEST_OPTIONS.set_want_large_tests(args.include_large)


def set_test_config_flags(args):
  # Tests that fail should only be run if explicitly requested.
  FAIL.set_should_include_by_default(args.include_failing)

  # Tests that are large should only be run if explicitly requested.
  LARGE.set_should_include_by_default(args.include_large)

  # Tests that timeout should not run unless explicitly requested.
  TIMEOUT.set_should_not_run(not args.include_timeouts)

  # Tests that are not supported should never be run.
  NOT_SUPPORTED.set_should_not_run(True)

  # Test that require OpenGL should not run if it is not supported.
  REQUIRES_OPENGL.set_should_not_run(not TEST_OPTIONS.supports_opengl)


def set_test_global_state(args):
  # Set/reset any global state involved in running the tests.
  # These settings need to be made for consistency, and allow the test framework
  # itself to be tested.
  retry_count = 0
  if TEST_OPTIONS.is_buildbot:
    retry_count = BOT_TEST_SUITE_MAX_RETRY_COUNT
  if args.keep_running:
    retry_count = sys.maxint
  test_driver.TestDriver.set_global_retry_timeout_run_count(retry_count)


def _prepare_output_directory(args):
  if args.output_dir:
    SuiteRunnerBase.set_output_directory(args.output_dir)
  if os.path.exists(SuiteRunnerBase.get_output_directory()):
    shutil.rmtree(SuiteRunnerBase.get_output_directory())
  build_common.makedirs_safely(SuiteRunnerBase.get_output_directory())


def _run_suites_and_output_results_remote(args, raw_args):
  """Runs test suite on remote host, and returns the status code on exit.

  First of all, this runs "prepare" locally, to set up some files for testing.
  Then, sends command to run test on remote host.

  Returns the status code of the program. Specifically, 0 on success.
  """
  if not prepare_suites(args):
    return 1
  raw_args.append('--noprepare')
  return remote_executor.run_remote_integration_tests(
      args, raw_args, get_configs_for_integration_tests())


def _run_suites_and_output_results_local(test_driver_list, args):
  """Runs integration tests locally and returns the status code on exit."""
  run_result = _run_suites(test_driver_list, args)
  test_failed, passed, total = util.test.suite_results.summarize()

  if args.cts_bot:
    if total > 0:
      dashboard_submit.queue_data('cts', 'count', {
          'passed': passed,
          'total': total,
      })
      dashboard_submit.queue_data('cts%', 'coverage%', {
          'passed': passed * 100. / total,
      })
    # In case of CTS bot, failure should not fail a step.
    return 0

  return 0 if run_result and not test_failed else 1


def _process_args(raw_args):
  args = parse_args(raw_args)
  logging.basicConfig(
      level=logging.DEBUG if args.output == 'verbose' else logging.WARNING)

  OPTIONS.parse_configure_file()

  # Limit to one job at a time when running a suite multiple times.  Otherwise
  # suites start interfering with each others operations and bad things happen.
  if args.repeat_runs > 1:
    args.jobs = 1

  if args.buildbot and OPTIONS.weird():
    args.exclude_patterns.append('cts.*')

  # Fixup all patterns to at least be a prefix match for all tests.
  # This allows options like "-t cts.CtsHardwareTestCases" to work to select all
  # the tests in the suite.
  args.include_patterns = [(pattern if '*' in pattern else (pattern + '*'))
                           for pattern in args.include_patterns]
  args.exclude_patterns = [(pattern if '*' in pattern else (pattern + '*'))
                           for pattern in args.exclude_patterns]

  set_test_options(args)
  set_test_config_flags(args)
  set_test_global_state(args)

  if (not args.remote and args.buildbot and
      not platform_util.is_running_on_cygwin()):
    print_chrome_version()

  if platform_util.is_running_on_remote_host():
    args.run_ninja = False

  return args


def main(raw_args):
  args = _process_args(raw_args)

  if args.run_ninja:
    build_common.run_ninja()

  test_driver_list = []
  for n in xrange(args.repeat_runs):
    test_driver_list.extend(_get_test_driver_list(args))

  if args.plan_report:
    util.test.suite_results.initialize(test_driver_list, args, False)
    report_expected_results(driver.scoreboard for driver in test_driver_list)
    return 0
  elif args.list:
    list_fully_qualified_test_names(
        (driver.scoreboard for driver in test_driver_list), args)
    return 0
  elif args.remote:
    return _run_suites_and_output_results_remote(args, raw_args)
  else:
    return _run_suites_and_output_results_local(test_driver_list, args)


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
