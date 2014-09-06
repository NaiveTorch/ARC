# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Provides functions for running Chrome on a remote Mac device.

import subprocess
import build_common
from util import remote_executor_util


def launch_remote_chrome(parsed_args, argv):
  executor = remote_executor_util.create_remote_executor(parsed_args)
  try:
    executor.rsync(
        remote_executor_util.get_launch_chrome_files_and_directories(
            parsed_args),
        executor.get_remote_arc_root())
    command = ' '.join(
        ['cd', executor.get_remote_arc_root(), '&&',
         remote_executor_util.SYNC_CHROME, '--verbose', '&&',
         remote_executor_util.SYNC_ADB, '--target=mac-x86_64', '&&'] +
        build_common.get_launch_chrome_command(
            remote_executor_util.create_launch_remote_chrome_param(argv)))
    executor.run_with_filter(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode


def run_remote_integration_tests(parsed_args, argv,
                                 configs_for_integration_tests):
  executor = remote_executor_util.create_remote_executor(
      parsed_args, enable_pseudo_tty=not parsed_args.buildbot)
  try:
    executor.rsync(
        remote_executor_util.get_integration_test_files_and_directories() +
        configs_for_integration_tests,
        executor.get_remote_arc_root())

    command = ' '.join(
        ['cd', executor.get_remote_arc_root(), '&&',
         remote_executor_util.SYNC_CHROME, '--verbose', '&&',
         remote_executor_util.SYNC_ADB, '--target=mac-x86_64', '&&',
         './run_integration_tests'] +
        remote_executor_util.create_launch_remote_chrome_param(argv) +
        # Some tests rely on the error message, which can be localized.
        # So here, set lang=en_US to avoid such message mismatching.
        ['--launch-chrome-opt=--lang=en_US'])
    executor.run(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode
