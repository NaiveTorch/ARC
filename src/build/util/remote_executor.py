#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Provides functions for running Chrome and dalvik tests on a remote host.

import argparse
import os.path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import build_common
from util import platform_util
from util import remote_chromeos_executor
from util import remote_executor_util
from util import remote_mac_executor
from util import remote_windows_executor


def _get_win_chrome_exe_path():
  return os.path.join(build_common.get_arc_root(),
                      build_common.get_chrome_prebuilt_path(),
                      'chrome.exe')


def _get_mac_chrome_exe_path():
  return os.path.join(build_common.get_arc_root(),
                      build_common.get_chrome_prebuilt_path(),
                      'Chromium.app/Contents/MacOS/Chromium')


def _get_chrome_exe_path_on_remote_host():
  """If this script is running on remote host, returns the path to Chrome."""
  if platform_util.is_running_on_chromeos():
    return remote_chromeos_executor.get_chrome_exe_path()
  if platform_util.is_running_on_cygwin():
    return _get_win_chrome_exe_path()
  if platform_util.is_running_on_mac():
    return _get_mac_chrome_exe_path()
  raise NotImplementedError(
      'get_chrome_exe_path_on_remote_host is supported only for Chrome OS, '
      'Cygwin, and Mac.')


def get_chrome_exe_path():
  """Returns the chrome path based on the platform the script is running on."""
  if platform_util.is_running_on_remote_host():
    return _get_chrome_exe_path_on_remote_host()
  return build_common.get_chrome_exe_path_on_local_host()


def resolve_path(path):
  if platform_util.is_running_on_cygwin():
    # As relative path on cygwin, which is passed to Chrome via an environment
    # variable or a flag, is not resolved by Chrome on Windows,
    # it is necessary to resolve beforehand.
    return remote_windows_executor.resolve_cygpath(path)
  return path


def maybe_extend_remote_host_chrome_params(parsed_args, params):
  """Adds chrome flags for Chrome on remote host, if necessary."""
  if platform_util.is_running_on_chromeos():
    remote_chromeos_executor.extend_chrome_params(parsed_args, params)
  if platform_util.is_running_on_cygwin():
    remote_windows_executor.extend_chrome_params(parsed_args, params)


def add_remote_arguments(parser):
  parser.add_argument('--remote', help='The IP address of the remote host, '
                      'which is either a Chrome OS device running a test '
                      'image, MacOS, or cygwin\'s sshd on Windows.')
  parser.add_argument('--ssh-key', help='The ssh-key file to login to remote '
                      'host. Used only when --remote option is specified.')


def copy_remote_arguments(parsed_args, args):
  if parsed_args.remote:
    args.append('--remote=' + parsed_args.remote)
  if parsed_args.ssh_key:
    args.append('--ssh-key=' + parsed_args.ssh_key)


def launch_remote_chrome(parsed_args, argv):
  remote_host_type = remote_executor_util.get_remote_host_type(parsed_args)
  if remote_host_type == 'chromeos':
    return remote_chromeos_executor.launch_remote_chrome(parsed_args, argv)
  if remote_host_type == 'cygwin':
    return remote_windows_executor.launch_remote_chrome(parsed_args, argv)
  if remote_host_type == 'mac':
    return remote_mac_executor.launch_remote_chrome(parsed_args, argv)
  raise NotImplementedError(
      'launch_remote_chrome is supported only for Chrome OS, Cygwin, and Mac.')


def run_remote_unittest(parsed_args, copied_files):
  remote_host_type = remote_executor_util.get_remote_host_type(parsed_args)
  if remote_host_type == 'chromeos':
    return remote_chromeos_executor.run_remote_unittest(
        parsed_args, copied_files)
  raise NotImplementedError(
      'run_remote_unittest is only supported for Chrome OS.')


def run_remote_integration_tests(parsed_args, argv,
                                 configs_for_integration_tests):
  remote_host_type = remote_executor_util.get_remote_host_type(parsed_args)
  if remote_host_type == 'chromeos':
    return remote_chromeos_executor.run_remote_integration_tests(
        parsed_args, argv, configs_for_integration_tests)
  if remote_host_type == 'cygwin':
    return remote_windows_executor.run_remote_integration_tests(
        parsed_args, argv, configs_for_integration_tests)
  if remote_host_type == 'mac':
    return remote_mac_executor.run_remote_integration_tests(
        parsed_args, argv, configs_for_integration_tests)
  raise NotImplementedError(
      'run_remote_integration_tests is only supported for Chrome OS, Cygwin, '
      'and Mac.')


def cleanup_remote_files(parsed_args):
  remote_host_type = remote_executor_util.get_remote_host_type(parsed_args)
  if remote_host_type == 'chromeos':
    return remote_chromeos_executor.cleanup_remote_files(parsed_args)
  raise NotImplementedError(
      'cleanup_remote_files is only supported for Chrome OS.')


def main():
  parser = argparse.ArgumentParser(description='remote executor')
  parser.add_argument('command', choices=('cleanup_remote_files',),
                      help='Specify the command to run in remote host.')
  parser.add_argument('--verbose', '-v', action='store_true',
                      help='Show verbose logging.')
  add_remote_arguments(parser)
  parsed_args = parser.parse_args()
  if parsed_args.command == 'cleanup_remote_files':
    return cleanup_remote_files(parsed_args)
  else:
    sys.exit('Unknown command: ' + parsed_args.command)


if __name__ == '__main__':
  sys.exit(main())
