#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This file is a part of the Dalvik test infrastructure for ARC.
# It contains helper routines for running dalvikvm in system mode.
#

import os
import re
import subprocess
import threading
import time
import traceback

import filtered_subprocess
import toolchain
from util import output_handler
from util.test.suite_runner import SuiteRunnerBase
from util.test.suite_runner import LAUNCH_CHROME_FLAKE_RETRY_COUNT

_ADB_SERVICE_PATTERN = re.compile(
    'I/AdbService:\s+(?:(emulator\-\d+)|Failed to start)')
_SYSTEM_MODE_PREFIX = 'system_mode.'


class SystemModeError(Exception):
  """SystemMode class raised in this module."""


class SystemModeLogs:
  def __init__(self):
    self._adb_logs = []
    self._chrome_logs = []

  def add_to_chrome_log(self, message):
    self._chrome_logs.append(message)

  def add_to_adb_log(self, message):
    self._adb_logs.append(message)

  def get_log(self):
    separator = '\n' + '=' * 30 + ' adb command logs ' + '=' * 30 + '\n'
    return ''.join(self._adb_logs) + separator + ''.join(self._chrome_logs)


class SystemModeThread(threading.Thread):
  def __init__(self, logs, suite_runner, additional_launch_chrome_opts):
    threading.Thread.__init__(self)
    self._suite_runner = suite_runner
    self._name = suite_runner.name
    self._additional_launch_chrome_opts = additional_launch_chrome_opts

    self._adb_service_is_initializing = True
    self._android_serial = None
    self._chrome = None
    self._event = threading.Event()
    self._has_error = False
    self._logs = logs
    self._shutdown = False

  def wait_for_adb(self):
    if not self._event.wait(30):
      self._adb_service_is_initializing = False

  def is_ready(self):
    return self._android_serial is not None

  def run(self):
    default_launch_chrome_opts = ['--stderr-log=I', '--nocrxbuild']
    args = self._suite_runner.get_launch_chrome_command(
        default_launch_chrome_opts + self._additional_launch_chrome_opts,
        mode='system',
        name_override=_SYSTEM_MODE_PREFIX + self._name)
    xvfb_output_filename = None
    if self._suite_runner.get_use_xvfb():
      output_directory = SuiteRunnerBase.get_output_directory()
      xvfb_output_filename = os.path.abspath(
          os.path.join(output_directory, self._name + '-system-mode-xvfb.log'))
      args = SuiteRunnerBase.get_xvfb_args(xvfb_output_filename) + args
    self._chrome = filtered_subprocess.Popen(args)
    self._chrome.run_process_filtering_output(self)

  def handle_stderr(self, line):
    self._logs.add_to_chrome_log(line)
    if output_handler.is_crash_line(line) or output_handler.is_exit_line(line):
      self._logs.add_to_adb_log('chrome unexpectedly exited '
                                'with line: %s' % line)
      self._event.set()
      self._has_error = True
      # Shutdown Chrome when plugin crash or exit is detected.
      self._shutdown = True
      return

    if not self._adb_service_is_initializing:
      return

    result = _ADB_SERVICE_PATTERN.match(line)
    if not result:
      return
    # Set a serial name like emulator-5554 if succeeded, otherwise None.
    self._android_serial = result.group(1)
    if self._android_serial:
      self._logs.add_to_adb_log('ARC adb service serial number is %s\n' %
                                self._android_serial)
    else:
      self._has_error = True
      self._logs.add_to_adb_log('ARC adb service failed to start.\n')

    self._adb_service_is_initializing = False
    self._event.set()

  def handle_stdout(self, line):
    # Pass everything to handle_stderr() because all stderr outputs are
    # rerouted to stdout on running over xvfb-run.
    self.handle_stderr(line)

  def handle_timeout(self):
    self._has_error = True
    self.start_shutdown()

  def is_done(self):
    return self._shutdown

  def start_shutdown(self):
    self._shutdown = True

  def shutdown(self):
    # Give Chrome 10 seconds to finish, otherwise kill the process.
    self.join(10)
    if self.isAlive() and self._chrome:
      self._logs.add_to_adb_log('SystemMode.__exit__: Killing Chrome process\n')
      self._chrome.terminate()
      time.sleep(5)
      if self._chrome.poll() is None:
        self._chrome.kill()

  def get_android_serial(self):
    return self._android_serial

  def has_error(self):
    return self._has_error


class SystemMode:
  """A class to manage ARC system mode for integration tests.

  Example:

    from util.test.suite_runner import SuiteRunnerBase
    from util.test.system_mode import SystemMode

    class MyTestRunner(SuiteRunnerBase):
      ...

      def run(self, unused_test_methods_to_run):
        with SystemMode(self) as arc:
          print arc.run_adb(['shell', 'echo', 'hello'])
        if arc.has_error():
          raise TimeoutError(arc.get_log())
        ...
  """

  def __init__(self, suite_runner, additional_launch_chrome_opts=[]):
    self._suite_runner = suite_runner
    self._name = suite_runner.name
    self._additional_launch_chrome_opts = additional_launch_chrome_opts

    self._adb = toolchain.get_tool('host', 'adb')
    self._has_error = False
    self._logs = SystemModeLogs()
    self._thread = SystemModeThread(self._logs,
                                    self._suite_runner,
                                    self._additional_launch_chrome_opts)

  def __enter__(self):
    # TODO(crbug.com/359859): Remove this hack when it is no longer necessary.
    # Workaround for what we suspect is a problem with Chrome failing on launch
    # a few times a day on the waterfall.  The symptom is that we get 3-5 lines
    # of raw output with no indication of the plugin being loaded or the ADB
    # service starting.
    chrome_flake_retry = LAUNCH_CHROME_FLAKE_RETRY_COUNT
    while True:
      self._thread.start()
      self._thread.wait_for_adb()
      if self._thread.is_ready():
        break
      else:
        self._thread.shutdown()
        if chrome_flake_retry == 0:
          self._logs.add_to_adb_log('timeout waiting to get adb '
                                    'serial number.\n')
          self._has_error = True
          return self
        else:
          self._logs.add_to_adb_log('Chrome crashed before getting adb '
                                    'serial number. Retrying.\n')
          self._thread = SystemModeThread(self._logs,
                                          self._suite_runner,
                                          self._additional_launch_chrome_opts)
        chrome_flake_retry -= 1

    try:
      self._logs.add_to_adb_log(self._suite_runner.run_subprocess(
          [self._adb, 'devices'], omit_xvfb=True))
      self.run_adb(['wait-for-device'])
    except:
      # To handle errors easily, we just ignore possible exceptions here,
      # and append stack traces to the log. As a result, the first run_adb()
      # may raise, and __exit__() records it for get_log().
      # All users have to do is check has_error() and call get_log() to catch
      # all error reports.
      # Note that considering the following scenario, a test inside "with"
      # statement may pass, but the log contains weird errors on adb.
      #  1) event.wait(30) above timed out, just before self._android_serial
      #     being set properly.
      #  2) At the same time, "adb devices" fails so an Exception is raised.
      #  3) self._android_serial is set in another thread.
      #  4) other run_adb() may work fine.
      self._logs.add_to_adb_log(traceback.format_exc())
      self._has_error = True
    return self

  def __shutdown(self):
    # Send shutdown request to the ARC system mode. It also guarantees to
    # make Chrome write enough output for filtered_subprocess to catch the
    # _shutdown flag.

    # Do nothing when the system mode can not find a target adb service to
    # avoid confusing errors in following adb commands.
    if not self._thread.is_ready():
      self._logs.add_to_adb_log('skip shutdown because adb did not start.\n')
      return
    try:
      self.run_adb(['shell', 'reboot', '-p'])
    except subprocess.CalledProcessError, e:
      # The reboot command above may fail with 255 when Chrome already finished
      # or crashed. We do not take 255 status code as an error.
      self._logs.add_to_adb_log(traceback.format_exc())
      self._has_error |= e.returncode != 255
    except:
      self._logs.add_to_adb_log(traceback.format_exc())
      self._has_error = True

  def __exit__(self, exc_type, exc_value, exc_traceback):
    self._thread.start_shutdown()
    self.__shutdown()
    self._thread.shutdown()

    # The log file is originally written by SuiteRunnerBase when
    # run_subprocess() is called. It is overwritten by following calls, and
    # only the last process can leave the log file.
    # SystemMode also runs Chrome inside the class, and unifying Chrome log
    # and subprocess logs in SuiteRunnerBase is not easy.
    # For now, we overwrite the default log file here.
    # TODO(crbug.com/356566): Stop overwriting the log here for simplifying.
    output_directory = SuiteRunnerBase.get_output_directory()
    output_filename = os.path.abspath(
        os.path.join(output_directory, self._name))
    with open(output_filename, 'w') as f:
      f.write(self.get_log())

    if exc_type:
      self._has_error = True
      # Do not catch SystemExit or KeyboardInterrupt.
      if exc_type in (SystemExit, KeyboardInterrupt):
        return False
    return True

  def run_adb(self, commands):
    """Runs an adb command and returns output.

    Returns single adb command's output. The output is also appended to
    the internal log container so that all logs can be obtained through
    get_log().
    """
    if not self._thread.is_ready():
      raise SystemModeError('adb is not currently serving.')

    try:
      args = [self._adb, '-s', self._thread.get_android_serial()] + commands
      self._logs.add_to_adb_log('SystemMode.run_adb: ' +
                                ' '.join(args) + '\n')
      result = self._suite_runner.run_subprocess(args, omit_xvfb=True)
      self._logs.add_to_adb_log(result + '\n')
      return result
    except:
      self._logs.add_to_adb_log('run_subprocess failed: ' +
                                traceback.format_exc())
      raise

  def get_log(self):
    return self._logs.get_log()

  def has_error(self):
    return self._has_error or self._thread.has_error()
