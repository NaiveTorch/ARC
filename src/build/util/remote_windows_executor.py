# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Provides functions for running Chrome and dalvik tests on a remote Windows
# machine.
#
# At the moment, we support running Chrome via cygwin's sshd.

import os
import subprocess

import build_common
import tempfile
from build_options import OPTIONS
from util import remote_executor_util

_DEFAULT_STDOUT_PREFIX = 'Chrome-NaCl-stdout'
_DEFAULT_STDERR_PREFIX = 'Chrome-NaCl-stdout'
_DEFAULT_NACLLOG_PREFIX = 'Chrome-NaCl-nacllog'

_REMOTE_ENV = {
    # Do not show restart dialog on crash.
    'CHROME_HEADLESS': '1',
}


def resolve_cygpath(path):
  """Returns the windows' absolute path from cygwin's relative path."""
  process = subprocess.Popen(['cygpath', '--windows', '--absolute', path],
                             stdout=subprocess.PIPE)
  return process.communicate()[0].strip()


def extend_chrome_params(parsed_args, params):
  # On Cygwin with 64bit Windows, stdout and stderr for NaCl are not supported
  # yet. (crbug.com/171836) In the mean time, we use a workaround by
  # redirecting the stdout and stderr to each file, and reading it by
  # "tail -f". "--no-sandbox" is needed for the redirection.
  # Note: two alternatives that are not chosen:
  # 1) Use named pipe: On cygwin, named pipe seems not well supported,
  # unfortunately. For example, cygwin's named pipe is not accessible from
  # native windows environment. Also, it is not easy to create/read windows
  # native named pipe from cygwin.
  # 2) Observe files by, e.g., inotify family or FindFirstChangeNotification:
  # At the moment, there seems no big merit, and these need more complicated
  # build system for windows.
  params.append('--no-sandbox')

  # Set each temporary file path for the redirection (if necessary).
  # os.tempnam may be insecure in general, but on cygwin, tempfile module seems
  # to have some race condition, when it is used to communicate between a
  # program running on Cygwin and one running on Windows native environment.
  os.environ.setdefault(
      'NACL_EXE_STDOUT',
      resolve_cygpath(os.tempnam(
          tempfile.gettempdir(), _DEFAULT_STDOUT_PREFIX)))
  os.environ.setdefault(
      'NACL_EXE_STDERR',
      resolve_cygpath(os.tempnam(
          tempfile.gettempdir(), _DEFAULT_STDERR_PREFIX)))
  os.environ.setdefault(
      'NACLLOG',
      resolve_cygpath(os.tempnam(
          tempfile.gettempdir(), _DEFAULT_NACLLOG_PREFIX)))


def _set_nacl_resource_permission(executor):
  # On Windows, NaCl cannot open resources without executable bit.
  # So, here, we manually set it regardless of the original permissions.
  resource_path = 'out/target/%s/runtime/_platform_specific/%s/' % (
      build_common.get_target_dir_name(OPTIONS.target()),
      OPTIONS.target())
  executor.run(' '.join([
      'cd', executor.get_remote_arc_root(), '&&',
      'chmod', '-R', 'a+x', resource_path]))


def _create_remote_executor(parsed_args, enable_pseudo_tty=False):
  return remote_executor_util.create_remote_executor(
      parsed_args, remote_env=_REMOTE_ENV, enable_pseudo_tty=enable_pseudo_tty)


def launch_remote_chrome(parsed_args, argv):
  executor = _create_remote_executor(parsed_args)
  try:
    executor.rsync(
        remote_executor_util.get_launch_chrome_files_and_directories(
            parsed_args),
        executor.get_remote_arc_root())
    _set_nacl_resource_permission(executor)

    # To launch arc successfully, it is necessary to set TMP env value
    # manually here (the param is usually delegated from the parent process).
    command = ' '.join(
        ['cd', executor.get_remote_arc_root(), '&&',
         remote_executor_util.SYNC_CHROME, '--verbose', '&&',
         remote_executor_util.SYNC_ADB, '--target=win-x86_64', '&&',
         executor.get_remote_env()] +
        build_common.get_launch_chrome_command(
            remote_executor_util.create_launch_remote_chrome_param(argv)))
    executor.run_with_filter(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode


def run_remote_integration_tests(parsed_args, argv,
                                 configs_for_integration_tests):
  executor = _create_remote_executor(
      parsed_args, enable_pseudo_tty=not parsed_args.buildbot)
  try:
    executor.rsync(
        remote_executor_util.get_integration_test_files_and_directories() +
        configs_for_integration_tests,
        executor.get_remote_arc_root())
    _set_nacl_resource_permission(executor)

    command = ' '.join(
        ['cd', executor.get_remote_arc_root(), '&&',
         remote_executor_util.SYNC_CHROME, '--verbose', '&&',
         remote_executor_util.SYNC_ADB, '--target=win-x86_64', '&&',
         executor.get_remote_env(),
         './run_integration_tests'] +
        remote_executor_util.create_launch_remote_chrome_param(argv) +
        # Some tests rely on the error message, which can be localized.
        # So here, set lang=en_US to avoid such message mismatching.
        ['--launch-chrome-opt=--lang=en_US'])
    executor.run(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode
