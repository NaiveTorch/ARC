#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This is a script for running a unit tests locally or remotely on a Chrome OS
# device.
#
# Usage:
# Run unit tests locally:
# $ src/build/util/test/run_unittest.py test0 test1 ...
#
# Run unit tests remotely on a Chrome OS device.
# $ src/build/util/test/run_unittest.py test0 test1 ... --remote=<REMOTE>
#
# When --remote is specified, the test binaries and other necessary files are
# copied to the remote Chrome OS device. The the unit tests need to be built
# before running this script.

import argparse
import json
import os
import shlex
import subprocess
import sys
import string

sys.path.insert(0, 'src/build')
import build_common
import build_options
import toolchain
import util.platform_util
import util.remote_executor
import util.test.unittest_util


def _read_test_info(filename):
  test_info_path = build_common.get_remote_unittest_info_path(filename)
  if not os.path.exists(test_info_path):
    return None
  with open(test_info_path, 'r') as f:
    return json.load(f)


def _construct_command(test_info):
  variables = test_info['variables'].copy()
  variables.setdefault('argv', '')
  variables.setdefault('qemu_arm', '')

  if util.platform_util.is_running_on_chromeos():
    # On ChromeOS, binaries in directories mounted with noexec options are
    # copied to the corresponding directories mounted with exec option.
    # Change runner to use the binaries under the directory mounted with exec
    # option.
    # Also do not use qemu_arm when running on ARM Chromebook.
    arc_root_with_exec = toolchain.get_chromeos_arc_root_with_exec()
    if build_options.OPTIONS.is_arm():
      variables['qemu_arm'] = ''
      variables['runner'] = ' '.join(
          toolchain.get_bare_metal_runner(use_qemu_arm=False,
                                          bin_dir=arc_root_with_exec))
      # Update --gtest_filter to re-enable the tests disabled only on qemu.
      if variables.get('qemu_disabled_tests'):
        variables['gtest_options'] = '--gtest_color=yes'
        if variables.get('disabled_tests'):
          variables['gtest_options'] = (
              ' --gtest_filter=-' + variables['disabled_tests'])
    else:
      variables['runner'] = ' '.join(
          toolchain.get_nacl_runner(
              build_options.OPTIONS.get_target_bitsize(),
              bin_dir=arc_root_with_exec))
    build_dir = build_common.get_build_dir()
    # Use test binary in the directory mounted with exec.
    variables['in'] = variables['in'].replace(
        build_dir, os.path.join(arc_root_with_exec, build_dir))
    # plugin_load_test specifies shared objects under buid_dir, which is
    # mounted with noexec option, so argv needs to be modified to point to
    # paths of filesystem mounted with exec.
    variables['argv'] = variables['argv'].replace(
        build_dir, os.path.join(arc_root_with_exec, build_dir))

  # Test is run as a command to build a test results file.
  command_template = string.Template(test_info['command'])
  return command_template.substitute(variables)


def _run_unittest(tests, verbose):
  """Runs the unit tests specified in test_info.

  This can run unit tests without depending on ninja and is mainly used on the
  remote device where ninja is not installed.
  """
  failed_tests = []
  unfound_tests = []
  for test in tests:
    index = 1
    while True:
      test_info = _read_test_info('%s.%d.json' % (test, index))
      if not test_info:
        # The format of test info file is [test name].[index].json, where index
        # is one of consecutive numbers from 1. If the test info file for index
        # 1 is not found, that means the corresponding test does not exist.
        if index == 1:
          unfound_tests.append(test)
        break
      command = _construct_command(test_info)
      if verbose:
        print 'Running:', command
      returncode = subprocess.call(shlex.split(command))
      if returncode != 0:
        print 'FAILED: ' + test
        failed_tests.append('%s.%d' % (test, index))
      index += 1
  if unfound_tests:
    print 'The following tests were not found: \n' + '\n'.join(unfound_tests)
  if failed_tests:
    print 'The following tests failed: \n' + '\n'.join(failed_tests)
  if unfound_tests or failed_tests:
    return -1
  return 0


def main():
  build_options.OPTIONS.parse_configure_file()

  description = 'Runs unit tests, verifying they pass.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('tests', metavar='test', nargs='*',
                      help=('The name of a unit test, such as libcommon_test.'
                            'If tests argument is not given, all unit tests '
                            'are run.'))
  parser.add_argument('-v', '--verbose', action='store_true',
                      default=False, dest='verbose',
                      help=('Show verbose output, including commands run'))
  util.remote_executor.add_remote_arguments(parser)
  parsed_args = parser.parse_args()

  if not parsed_args.tests:
    parsed_args.tests = util.test.unittest_util.get_all_tests()

  if parsed_args.remote:
    return util.remote_executor.run_remote_unittest(parsed_args)
  else:
    return _run_unittest(parsed_args.tests, parsed_args.verbose)


if __name__ == '__main__':
  sys.exit(main())
