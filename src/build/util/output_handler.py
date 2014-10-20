# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Defines several output handlers used for filtered_subprocess.

import logging
import re
import subprocess
import time
import sys
from build_options import OPTIONS

import crash_analyzer
from util import platform_util
from util.test.atf_instrumentation_result_parser import \
    ATFInstrumentationResultParser


# NaCl waits 7s before writing validation cache.
_CACHE_WARMING_CHROME_KILL_DELAY = 7

# Regular expressions used for checking output results.
_CRASH_RE = re.compile(
    r'Signal [0-9]+ from untrusted code: pc=|'
    r'Sending shut-down message!|'
    r'INFO:CONSOLE.*FINISHED REPORTING CRASH|'
    r'INFO:CONSOLE.*PING TIMEOUT|'
    r'VM aborting')
_ABNORMAL_EXIT_RE = re.compile(
    r'NaCl untrusted code called _exit\(0x[^0]|'
    r'INFO:CONSOLE.*Activity stack is empty\. Shutting down\.|'
    r'No GPU support\.')
# E.g., at java.lang.reflect.Method.invokeNative(Native Method)
_JAVA_EXCEPTION_RE = re.compile(r'\tat [a-z].*\)\n')


def is_crash_line(line):
  return bool(_CRASH_RE.search(line))


def is_abnormal_exit_line(line):
  return bool(_ABNORMAL_EXIT_RE.search(line))


def is_java_exception_line(line):
  return bool(_JAVA_EXCEPTION_RE.search(line))


def _get_process_stat_line(pid):
  with open('/proc/%d/stat' % pid) as f:
    line = f.readlines()[0]
    return line


def _get_process_parent_pid(pid):
  parent_pid = int(_get_process_stat_line(pid).split()[3])
  return parent_pid


def _is_descendent_of_pid(pid, ancestor):
  while pid != 0:
    pid = _get_process_parent_pid(pid)
    if pid == ancestor:
      return True
  return False


def _get_app_mem_info(pid):
  """Returns a pair (res, virt) showing the process memory usage in MB."""
  stat = _get_process_stat_line(pid).split()
  res = float(stat[23]) * 4096 / 1024 / 1024
  # On NaCl, hide uselessly and confusingly big vsize due to memory mapping.
  virt = 0 if OPTIONS.is_nacl_build() else float(stat[22]) / 1024 / 1024
  return (res, virt)


def _find_nacl_helper_pids(chrome_pid):
  pids = subprocess.check_output(['pgrep', 'nacl_helper']).split()
  results = []
  for pid in pids:
    pid = int(pid)
    if _is_descendent_of_pid(pid, chrome_pid):
      results.append(pid)
  return results


def _get_nacl_arc_process_memory(chrome_pid):
  """Returns (res, virt) pair of the ARC nacl_helper process."""
  # Take some extreme measures to get the memory usage of nacl_helper.
  # From the untrusted code we cannot know the amount of memory used,
  # we cannot even know what our process' pid is.  So we search for all the
  # nacl_helper processes spawned from the Chrome we created (there will be
  # two), and we assume the one with more resident memory is the one actively
  # running ARC.  Note that this is the absolute amount of used memory.
  # In trusted mode when we print out RSS, we are printing the delta RSS since
  # our plugin started.
  #
  # TODO(crbug.com/320266): Remove these awful heuristics once the app can
  # report out the resident usage itself.
  pids = _find_nacl_helper_pids(chrome_pid)
  # There are 2 nacl_helpers in NaCl, 3 in BareMetal.
  if len(pids) not in (2, 3):
    return None
  res, virt = max([_get_app_mem_info(pid) for pid in pids])
  if virt:
    sys.stderr.write(
        'NaCl ARC process memory: resident %dMB, virtual %dMB\n' % (res, virt))
  else:
    sys.stderr.write('NaCl ARC process memory: resident %dMB\n' % res)
  return (res, virt)


class OutputDumper(object):
  def __init__(self, parsed_args):
    self.parsed_args = parsed_args
    # List of lines for stdout/stderr Chrome output to suppress.
    self.LINE_SUPPRESS = [
        # Problems with gPrecise ALSA give PCM 'underrun occurred' messages
        # even when stopped in the debugger sometimes.
        'underrun occurred',
        # When debugging with gdb, NaCl is emitting many of these messages.
        'NaClAppThreadSetSuspendedRegisters: Registers not modified']

  def handle_timeout(self):
    pass

  def handle_stdout(self, line):
    if self.suppress_output(line):
      return
    sys.stdout.write(line)

  def handle_stderr(self, line):
    if self.suppress_output(line):
      return
    sys.stderr.write(line)

  def get_error_level(self, child_level):
    return child_level

  def is_done(self):
    return False

  def suppress_output(self, line):
    for suppress in self.LINE_SUPPRESS:
      if suppress in line:
        return True
    return False


class ATFTestHandler(object):
  # TODO(crbug.com/254164): Remove this awful compat test pattern
  # once NDK tests no longer use it.
  # Note that there are a few variations in what prints based on what JUnit
  # style testrunner/testreporter is used.
  _COMPAT_TEST_PATTERN = re.compile(r'OK \(\d+ test(s)?\)')
  _COMPAT_FAILURES_PATTERN = re.compile(r'FAILURES!!!')

  def __init__(self):
    self._reached_done = False
    self._instrumentation_result_parser = ATFInstrumentationResultParser()

    # Can be True (passed), False (failed), or None (unknown)
    self.compatibility_result_passed = None

  def _get_test_methods_passed(self):
    if self._instrumentation_result_parser.output_recognized:
      return self._instrumentation_result_parser.test_methods_passed
    if self.compatibility_result_passed is True:
      return 1
    return 0

  def _get_test_methods_failed(self):
    if self._instrumentation_result_parser.output_recognized:
      return self._instrumentation_result_parser.test_methods_failed
    if self.compatibility_result_passed is False:
      return 1
    return 0

  def _get_test_methods_total(self):
    if self._instrumentation_result_parser.output_recognized:
      return self._instrumentation_result_parser.test_methods_total
    if self.compatibility_result_passed is not None:
      return 1
    return None

  def _dump_test_method_results(self):
    total = self._get_test_methods_total()
    # TODO(crbug.com/254164): Require this to be set.
    if total is not None:
      passed = self._get_test_methods_passed()
      failed = self._get_test_methods_failed()
      print('TEST METHOD RESULTS: %d pass, %d fail, %d incomplete' %
            (passed, failed, total - passed - failed))

  def handle_timeout(self):
    if not self._reached_done:
      self._dump_test_method_results()
      print '[  TIMEOUT  ]'
      sys.exit(1)

  def get_error_level(self, child_level):
    self._dump_test_method_results()
    if child_level == 0 and (self._get_test_methods_passed() ==
                             self._get_test_methods_total()):
      print '[  PASSED  ]'
      return 0
    else:
      print '[  FAILED  ]'
      return 1

  def is_done(self):
    return self._reached_done

  def handle_stderr(self, line):
    sys.stderr.write(line)
    return self._handle_line(line)

  def handle_stdout(self, line):
    sys.stderr.write(line)
    return self._handle_line(line)

  def _handle_compat_line(self, line):
    # TODO(crbug.com/254164): Remove once the compatibility tests are gone.
    if self._COMPAT_TEST_PATTERN.search(line):
      self.compatibility_result_passed = True
      self._reached_done = True
    elif self._COMPAT_FAILURES_PATTERN.search(line):
      self.compatibility_result_passed = False
      self._reached_done = True

  def _handle_line(self, line):
    if is_crash_line(line) or is_abnormal_exit_line(line):
      self._reached_done = True
      return False

    # Try to parse a line as message output from "am instrument -r" command.
    # If a preceding line is handled, the parser has the responsibility to
    # parse all the lines.
    if (self._instrumentation_result_parser.process_line(line) or
        self._instrumentation_result_parser.output_recognized):
      if self._instrumentation_result_parser.run_completed_cleanly:
        self._reached_done = True
      return False

    # Then, finally fallback to compatibility tests.
    self._handle_compat_line(line)
    return False


class PerfTestHandler(object):
  def __init__(self, parsed_args, stats, chrome_process, cache_warming=False):
    self.parsed_args = parsed_args
    self.in_exception = False
    self.last_line = ''
    self.any_errors = False
    self.reached_done = False
    self.stats = stats
    self.cache_warming = cache_warming
    self.full_output = []
    self.resumed_time = None
    self.chrome_process = chrome_process

  def handle_timeout(self):
    if not self.reached_done:
      if self.resumed_time:
        self._finish()
        return
      if not self.parsed_args.verbose:
        for line in self.full_output:
          print line.rstrip()
      print '[  TIMEOUT  ]'
      sys.exit(1)

  def _handle_line_common(self, line):
    self.full_output.append(line)
    if is_crash_line(line) or is_abnormal_exit_line(line):
      sys.stderr.write(line)
      # TODO(crbug.com/397454): This sometimes happens in
      # perf_test.py. We should identify the actual cause of this
      # crash or fix this issue.
      if self.reached_done:
        logging.error('Crashed after the test finishes')
        return
      print '[  FAILED  ]'
      self.any_errors = True
      self.reached_done = True
      return
    if self.parsed_args.verbose:
      sys.stderr.write(line)

  def handle_stdout(self, line):
    self._handle_line_common(line)
    # Consider lines like these as part of exception stack traces:
    #      at android.os.Process ...
    #      ... 3 more
    if (is_java_exception_line(line) or
       (self.in_exception and re.search(r'^\t... \d', line))):
      if not self.in_exception:
        sys.stderr.write('\nException found:\n')
        self.in_exception = True
        self.any_errors = True
        sys.stderr.write(self.last_line)
        sys.stderr.write(line)
    else:
      self.in_exception = False
    self.last_line = line
    self._update_timeout()

  def handle_stderr(self, line):
    self._handle_line_common(line)
    if self.stats.parse_pre_plugin_perf_message(line):
      return

    if self.stats.parse_app_start_message(line):
      dash_line = '--------------------------------'
      sys.stderr.write(dash_line + '\n')
      sys.stderr.write(line)
      if platform_util.is_running_on_linux():
        app_mem = _get_nacl_arc_process_memory(self.chrome_process.pid)
        if app_mem:
          self.stats.app_res_mem = self.stats.app_res_mem or app_mem[0]
          self.stats.app_virt_mem = self.stats.app_virt_mem or app_mem[1]
      sys.stderr.write(dash_line + '\n')

      self.resumed_time = time.time()
      if self.parsed_args.minimum_lifetime:
        self.chrome_process.update_timeout(self.parsed_args.minimum_lifetime)
        return
      if self.parsed_args.mode == 'perftest' and self.cache_warming:
        # Wait for NaCl validation cache to flush before killing chrome.
        self.chrome_process.update_timeout(_CACHE_WARMING_CHROME_KILL_DELAY)
        return
      if not self.parsed_args.minimum_steady:
        self._finish()
    self._update_timeout()

  def _finish(self):
    if not self.any_errors:
      print '[  PASSED  ]'
    else:
      print '[  FAILED  ]'
    self.reached_done = True

  def _update_timeout(self):
    if not self.resumed_time or not self.parsed_args.minimum_steady:
      return
    secs_after_resumed = time.time() - self.resumed_time
    if secs_after_resumed > self.parsed_args.timeout:
      return
    self.chrome_process.update_timeout(self.parsed_args.minimum_steady)

  def is_done(self):
    return self.reached_done

  def get_error_level(self, child_level):
    if self.any_errors:
      return 1
    else:
      return 0


class ArcStraceFilter(object):
  def __init__(self, output_handler, output_filename):
    self._strace_output = open(output_filename, 'w', buffering=0)
    self._output_handler = output_handler
    self._arc_strace_pattern = re.compile(r'\[\[arc_strace\]\]: ')
    self._line_buffer = []

  def is_done(self):
    return self._output_handler.is_done()

  def handle_stdout(self, line):
    self._output_handler.handle_stdout(line)

  def handle_stderr(self, line):
    matched = self._arc_strace_pattern.search(line)
    if matched:
      # Found [[arc_strace]]: marker. Output to the file.
      self._strace_output.write(line[matched.end():])

      # Keep leading part if necessary. Note that the trailing LF is also
      # removed here intentionally, because it is a part of arc_strace log.
      # We don't output the line directly here, because it is necessary to
      # pass a line to the delegated output handler.
      start = matched.start()
      if start:
        self._line_buffer.append(line[:start])
    else:
      if self._line_buffer:
        line = ''.join(self._line_buffer) + line
        self._line_buffer = []
      self._output_handler.handle_stderr(line)

  def handle_timeout(self):
    self._output_handler.handle_timeout()

  def get_error_level(self, child_level):
    return self._output_handler.get_error_level(child_level)


class CrashAddressFilter(object):
  def __init__(self, output_handler):
    self._output_handler = output_handler
    self._crash_analyzer = crash_analyzer.CrashAnalyzer()

  def is_done(self):
    return self._output_handler.is_done()

  def handle_stdout(self, line):
    self._output_handler.handle_stdout(line)

  def handle_stderr(self, line):
    self._output_handler.handle_stderr(line)
    if self._crash_analyzer.handle_line(line):
      self._output_handler.handle_stderr(
          self._crash_analyzer.get_crash_report())

  def handle_timeout(self):
    self._output_handler.handle_timeout()

  def get_error_level(self, child_level):
    return self._output_handler.get_error_level(child_level)
