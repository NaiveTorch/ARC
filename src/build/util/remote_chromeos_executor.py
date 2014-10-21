# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Provides functions for running Chrome and dalvik tests on a remote ChromeOS
# device.

import atexit
import os
import re
import subprocess
import sys
import tempfile
import traceback

import build_common
import toolchain
from build_options import OPTIONS
from util import gdb_util
from util import launch_chrome_util
from util import remote_executor_util
from util.test import unittest_util

# The fake login name used when running Chrome remotely on a Chrome OS device.
_FAKE_TEST_USER = 'arc_fake_test_user@gmail.com'
# The environment variables that are set when running Chrome in the remote host.
_REMOTE_ENV = {
    'DISPLAY': ':0.0',
    # /var/tmp instead of /tmp is used here because /var/tmp uses the same
    # filesystem as that for /home/chronos, where user profile directory is
    # stored by default on Chrome OS. /tmp uses tmpfs and performance
    # characteristics might be different.
    'TMPDIR': '/var/tmp',
    'XAUTHORITY': '/home/chronos/.Xauthority',
}
# The existence of this file indicates the user is logged in.
_CHROMEOS_LOGGED_IN_FILE = '/var/run/state/logged-in'
# If this file exists, session_manager on Chrome OS does not restart Chrome when
# Chrome is killed.
_DISABLE_CHROME_RESTART_FILE = '/var/run/disable_chrome_restart'
# This holds the command line of Chrome browser process.
_CHROME_COMMAND_LINE_FILE = '/var/tmp/chrome_command_line'

_REMOTE_CHROME_EXE_BINARY = '/opt/google/chrome/chrome'
_REMOTE_NACL_HELPER_BINARY = '/opt/google/chrome/nacl_helper'

_UNNEEDED_PARAM_PREFIXES = (
    '--ash-default-wallpaper',
    '--ash-guest-wallpaper',
    '--device-management-url',
    '--enterprise',
    '--ppapi-flash',
    '--register-pepper-plugins',
    '--system-developer-mode',
    '--vmodule')


def _create_remote_executor(parsed_args, enable_pseudo_tty=False):
  return remote_executor_util.RemoteExecutor(
      'root', parsed_args.remote, remote_env=_REMOTE_ENV,
      ssh_key=parsed_args.ssh_key, enable_pseudo_tty=enable_pseudo_tty)


def _get_param_name(param):
  m = re.match(r'--([^=]+).*', param)
  if not m:
    return None
  return m.group(1)


def _is_param_set(checked_param, params):
  """Check if a command line parameter is specified in the list of parameters.

  Return True if |checked_param| is included in |params| regardless of the
  value of |checked_param|. For example, the following expression returns True.

      _is_param_set('--log-level=0', ['--log-level=2', '--enable-logging'])
  """
  checked_param_name = _get_param_name(checked_param)
  assert checked_param_name, 'Invalid param: ' + checked_param
  for param in params:
    param_name = _get_param_name(param)
    if checked_param_name == param_name:
      return True
  return False


def _setup_remote_arc_root(executor, copied_files):
  # Copy specified files to the remote host.
  executor.rsync(copied_files, executor.get_remote_arc_root())


def _copy_to_arc_root_with_exec(remote_arc_root, path):
  """Returns the command to copy the file or directory to a directory with exec.

  We copy executable files to a directory whose filesystem is mounted without
  noexec mount option, so that they can be executed directly.
  This returns the command for copying the file or directory under ARC root,
  which is mounted with noexec, to a directory mounted without noexec.
  """
  source = os.path.join(remote_arc_root, path)
  destination = toolchain.get_chromeos_arc_root_with_exec(os.path.dirname(path))
  return ' '.join(['mkdir', '-p', destination, '&&',
                   'rsync', '-tr', source, destination])


def _setup_remote_processes(executor):
  file_map = {
      'chrome_exe_file': _REMOTE_CHROME_EXE_BINARY,
      'command_line_file': _CHROME_COMMAND_LINE_FILE,
      'logged_in_file': _CHROMEOS_LOGGED_IN_FILE,
      'restart_file': _DISABLE_CHROME_RESTART_FILE,
  }
  commands = [
      # Force logging out if a user is logged in or
      # _DISABLE_CHROME_RESTART_FILE is left, which indicates the last session
      # did not finish cleanly.
      # TODO(mazda): Change this to a more reliable way.
      ('if [ -f %(logged_in_file)s -o -f %(restart_file)s ]; then '
       '  rm -f %(restart_file)s; restart ui; sleep 1s; '
       'fi'),
      # Disallow session_manager to restart Chrome automatically.
      'touch %(restart_file)s',
      # Remove the Chrome command line file in case it is left for any reason.
      'rm -f %(command_line_file)s',
      # Search the command line of browser process, which does not include
      # --type=[..] flag, then save the command line into a file.
      ('ps -a -x -oargs | '
       'grep "^%(chrome_exe_file)s " | '
       'grep --invert-match type= > %(command_line_file)s'),
      # Kill all the chrome processes launched by session_manager.
      'pkill -9 -P `pgrep session_manager` chrome$',
      # Mount Cryptohome as guest. Otherwise Chrome crashes during NSS
      # initialization. See crbug.com/401061 for more details.
      'cryptohome --action=mount_guest',
  ]
  executor.run_commands([command % file_map for command in commands])

  # Recover the chrome processes after the command ends
  atexit.register(lambda: _restore_remote_processes(executor))


def _restore_remote_processes(executor):
  print 'Restarting remote UI...'
  # Allow session_manager to restart Chrome and do restart.
  executor.run('rm -f %s %s && restart ui' % (_DISABLE_CHROME_RESTART_FILE,
                                              _CHROME_COMMAND_LINE_FILE))


def _setup_remote_environment(executor, copied_files):
  try:
    _setup_remote_arc_root(executor, copied_files)
    _setup_remote_processes(executor)
  except subprocess.CalledProcessError as e:
    # Print the stack trace if any preliminary command fails so that the
    # failing command can be examined easily, and rethrow the exception to pass
    # the exit code.
    traceback.print_exc()
    raise e


def get_chrome_exe_path():
  return _REMOTE_CHROME_EXE_BINARY


def launch_remote_chrome(parsed_args, argv):
  try:
    executor = _create_remote_executor(parsed_args)
    copied_files = (
        remote_executor_util.get_launch_chrome_files_and_directories(
            parsed_args) +
        [_get_adb_path()])
    _setup_remote_environment(executor, copied_files)
    if 'plugin' in parsed_args.gdb:
      nacl_helper_binary = parsed_args.nacl_helper_binary
      if not nacl_helper_binary:
        tmpdir = tempfile.gettempdir()
        executor.copy_remote_files([_REMOTE_NACL_HELPER_BINARY], tmpdir)
        nacl_helper_binary = os.path.join(tmpdir, 'nacl_helper')
      # This should not happen, but for just in case.
      assert os.path.exists(nacl_helper_binary)

      # -v: show the killed process, -w: wait for the killed process to die.
      executor.run('sudo killall -vw gdbserver', ignore_failure=True)
      gdb_util.launch_bare_metal_gdb_for_remote_debug(
          parsed_args.remote, executor.get_ssh_options(), nacl_helper_binary,
          parsed_args.gdb_type)
    executor.run(_copy_to_arc_root_with_exec(
        executor.get_remote_arc_root(), 'out/adb'))
    command = ' '.join(
        ['sudo', '-u', 'chronos',
         executor.get_remote_env()] +
        launch_chrome_util.get_launch_chrome_command(
            remote_executor_util.create_launch_remote_chrome_param(argv)))
    executor.run_with_filter(command)
  except subprocess.CalledProcessError as e:
    sys.exit(e.returncode)


def extend_chrome_params(parsed_args, params):
  # Do not show the New Tab Page because showing NTP during perftest makes the
  # benchmark score look unnecessarily bad especially on ARM Chromebooks where
  # CPU resource is very limited.
  # TODO(yusukes): Use this option on Windows/Mac/Linux too. We might need to
  # use --keep-alive-for-test then.
  params.append('--no-startup-window')

  # Login as a fake test user.
  params.append('--login-user=' + _FAKE_TEST_USER)

  if OPTIONS.is_arm() and parsed_args.mode in ('atftest', 'system'):
    # On ARM Chromebooks, there is a bug (crbug.com/270064) that causes X server
    # to hang when multiple ash host windows are displayed in the size of the
    # screen, which is the default ash host window size on Chrome OS. In order
    # to workaround this issue, show the ash host window in the size 1 pixel
    # wider than the original screen size.
    # TODO(crbug.com/314050): Remove the workaround once the upstream issue is
    # fixed.
    output = subprocess.check_output(['xdpyinfo', '-display', ':0.0'])
    m = re.search(r'dimensions: +([0-9]+)x([0-9]+) pixels', output)
    if not m:
      raise Exception('Cannot get the screen size')
    width, height = int(m.group(1)) + 1, int(m.group(2))
    params.append('--ash-host-window-bounds=0+0-%dx%d' % (width, height))

  assert os.path.exists(_CHROME_COMMAND_LINE_FILE), (
      '%s does not exist.' % _CHROME_COMMAND_LINE_FILE)
  with open(_CHROME_COMMAND_LINE_FILE) as f:
    chrome_command_line = f.read().rstrip()
  params_str = re.sub('^%s ' % _REMOTE_CHROME_EXE_BINARY, '',
                      chrome_command_line)
  # Use ' -' instead of ' ' to split the command line flags because the flag
  # values can contain spaces.
  new_params = params_str.split(' -')
  new_params[1:] = ['-' + param for param in new_params[1:]]

  # Check if _UNNEEDED_PARAM_PREFIXES is up to date.
  for unneeded_param in _UNNEEDED_PARAM_PREFIXES:
    if not any(p.startswith(unneeded_param) for p in new_params):
      print 'WARNING: _UNNEEDED_PARAM_PREFIXES is outdated. Remove %s.' % (
          unneeded_param)

  # Append the flags that are not set by our scripts.
  for new_param in new_params:
    if not _is_param_set(new_param, params) and _is_param_needed(new_param):
      params.append(new_param)


def _is_param_needed(param):
  if (param.startswith(_UNNEEDED_PARAM_PREFIXES) or
      # Do not show login screen
      param == '--login-manager'):
    return False
  return True


def _get_adb_path():
  return os.path.relpath(toolchain.get_adb_path_for_chromeos(),
                         build_common.get_arc_root())


def _copy_unittest_executables_to_arc_with_exec(executor, tests):
  """Copies executables for unit tests to a directory mounted with exec."""
  noexec_paths = [build_common.get_build_path_for_executable(test)
                  for test in tests]
  noexec_paths.append(build_common.get_load_library_path())
  noexec_paths.extend(unittest_util.get_nacl_tools())
  for noexec_path in noexec_paths:
    executor.run(_copy_to_arc_root_with_exec(
        executor.get_remote_arc_root(), noexec_path))


def run_remote_unittest(parsed_args):
  copied_files = remote_executor_util.get_unit_test_files_and_directories(
      parsed_args)
  try:
    executor = _create_remote_executor(parsed_args)
    _setup_remote_environment(executor, copied_files)
    _copy_unittest_executables_to_arc_with_exec(executor, parsed_args.tests)

    verbose = ['--verbose'] if parsed_args.verbose else []
    command = ' '.join(
        [executor.get_remote_env(), 'python',
         remote_executor_util.RUN_UNIT_TEST] + verbose +
        parsed_args.tests)
    executor.run(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode


def run_remote_integration_tests(parsed_args, argv,
                                 configs_for_integration_tests):
  try:
    executor = _create_remote_executor(
        parsed_args, enable_pseudo_tty=not parsed_args.buildbot)
    copied_files = (
        remote_executor_util.get_integration_test_files_and_directories() +
        [_get_adb_path()] +
        configs_for_integration_tests)
    _setup_remote_environment(executor, copied_files)
    _copy_unittest_executables_to_arc_with_exec(
        executor, unittest_util.get_all_tests())
    executor.run(_copy_to_arc_root_with_exec(
        executor.get_remote_arc_root(), 'out/adb'))
    command = ' '.join(
        ['sudo', '-u', 'chronos', executor.get_remote_env(),
         '/bin/sh', './run_integration_tests'] +
        remote_executor_util.create_launch_remote_chrome_param(argv))
    executor.run(command)
    return 0
  except subprocess.CalledProcessError as e:
    return e.returncode


def cleanup_remote_files(parsed_args):
  executor = _create_remote_executor(parsed_args)
  removed_patterns = [
      # ARC root directory in the remote host.
      executor.get_remote_arc_root(),
      # The directory executables are temporarily copied to.
      toolchain.get_chromeos_arc_root_with_exec(),
      # Temporary Chrome profile directories created for integration tests.
      # These sometimes remain after the tests finish for some reasons.
      os.path.join(executor.get_remote_tmpdir(),
                   build_common.CHROME_USER_DATA_DIR_PREFIX + '-*'),
  ]
  executor.run(' '.join(['rm', '-rf'] + removed_patterns), cwd='.')
