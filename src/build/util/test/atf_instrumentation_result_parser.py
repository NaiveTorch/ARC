# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import time

from util.test.test_method_result import TestMethodResult


class ATFInstrumentationResultParser(object):
  """This class processes ATF instrumentation status messages.

  When the Android "am instrument" command is used to run tests, and the "-r"
  flag is also used with the command, the instrumentation command handler will
  write out detailed status messages for each test that is run.

  This class detects those messages by processing the output of a run line by
  line, and can be used to determine information about the status of each test
  as well as the status of the run as a whole.
  """
  # Instrumentation (shortened here to "I13N") message patterns
  _I13N_PREFIX = 'INSTRUMENTATION_'
  _I13N_CURRENT_CLASS = re.compile(r'INSTRUMENTATION_STATUS: class=(\S+)$')
  _I13N_CURRENT_TEST = re.compile(r'INSTRUMENTATION_STATUS: test=(\S+)$')
  _I13N_TOTAL_TESTS = re.compile(r'INSTRUMENTATION_STATUS: numtests=(\d+)$')
  _I13N_CURRENT_TESTS = re.compile(r'INSTRUMENTATION_STATUS: current=(\d+)$')
  _I13N_STATUS_STREAM = re.compile(r'INSTRUMENTATION_STATUS: stream=(.*)$')
  _I13N_STATUS_OTHER = re.compile(r'INSTRUMENTATION_STATUS:')
  _I13N_RESULT_STREAM = re.compile(r'INSTRUMENTATION_RESULT: stream=(.*)$')
  _I13N_CODE = re.compile('INSTRUMENTATION_CODE: (-?\d+)$')
  _I13N_STATUS_CODE = re.compile(r'INSTRUMENTATION_STATUS_CODE: (-?\d+)')

  # Status codes as returned/displayed by ATF tests.
  _INCOMPLETE = 1
  _OK = 0
  _ERROR = -1
  _FAILURE = -2

  # Map from ATF test status code to TestMethodResult code.
  _METHOD_RESULT_MAP = {
      _INCOMPLETE: TestMethodResult.INCOMPLETE,
      _OK: TestMethodResult.PASS,
      _ERROR: TestMethodResult.FAIL,
      _FAILURE: TestMethodResult.FAIL,
  }

  # RESULT_CODE which instrumentation returns. See Activity.java.
  _RESULT_OK = -1
  _RESULT_CANCELED = 0
  _RESULT_FIRST_USER = 1

  def __init__(self):
    self._suite_code = None
    self._suite_message = None
    self._tests_total = None
    self._latest_result = None
    self._current_test_number = 0
    self._current_test_start_time = 0
    self._tests_passed = 0
    self._tests_failed = 0
    self._tests_running = 0
    self._test_fqn_to_result_map = {}
    self._multiline_stream = False
    self._recognized = False

    self._clear_current_values()

  def _clear_current_values(self):
    self._current_class = None
    self._current_test = None
    self._current_stream = None

  def _update_tests_counts_from_result(self, result):
    if result.failed:
      self._tests_failed += 1
      self._tests_running -= 1
    elif result.passed:
      self._tests_passed += 1
      self._tests_running -= 1
    elif result.incomplete:
      self._tests_running += 1

  def _get_current_stream_message(self):
    if self._current_stream is not None:
      return '\n'.join(self._current_stream)
    else:
      return ''

  def _handle_code(self, match):
    assert self._suite_code is None
    self._suite_code = int(match.group(1))
    self._suite_message = self._get_current_stream_message()

  def _handle_status_code(self, match):
    assert self._current_class is not None
    assert self._current_test is not None
    code = int(match.group(1))

    duration = 0
    if code == self._INCOMPLETE:
      self._current_test_start_time = time.time()
    else:
      duration = time.time() - self._current_test_start_time

    fqn = self._current_class + '#' + self._current_test
    assert (fqn not in self._test_fqn_to_result_map or
            self._test_fqn_to_result_map[fqn].incomplete)
    result = TestMethodResult(fqn, self._METHOD_RESULT_MAP[code],
                              self._get_current_stream_message(), duration)
    self._test_fqn_to_result_map[fqn] = result

    self._clear_current_values()

    self._update_tests_counts_from_result(result)
    self._latest_result = result

  def _handle_total_tests(self, match):
    count = int(match.group(1))
    assert self._tests_total is None or self._tests_total == count, (
        'Inconsistent test count encountered. Expected %d, observed %d' %
        (self._tests_total, count))
    self._tests_total = count

  def _handle_current_test(self, match):
    self._current_test_number = int(match.group(1))

  def _handle_class(self, match):
    self._current_class = match.group(1)

  def _handle_test(self, match):
    self._current_test = match.group(1)

  def _handle_other(self, match):
    pass

  def _handle_stream(self, match):
    self._current_stream = [match.group(1)]
    self._multiline_stream = True

  _HANDLERS = (
      (_I13N_CODE, _handle_code),
      (_I13N_STATUS_CODE, _handle_status_code),
      (_I13N_TOTAL_TESTS, _handle_total_tests),
      (_I13N_CURRENT_TESTS, _handle_current_test),
      (_I13N_CURRENT_CLASS, _handle_class),
      (_I13N_CURRENT_TEST, _handle_test),
      (_I13N_STATUS_STREAM, _handle_stream),
      (_I13N_STATUS_OTHER, _handle_other),
      (_I13N_RESULT_STREAM, _handle_stream),
  )

  def get_current_test_name(self):
    if not self._current_class or not self._current_test:
      return None
    return '%s#%s' % (self._current_class, self._current_test)

  def get_latest_result(self):
    return self._latest_result

  def _process_instrumentation_line(self, line):
    if line.startswith('INSTRUMENTATION_'):
      for regex, handler in self._HANDLERS:
        m = regex.match(line)
        if m:
          self._recognized = True
          self._multiline_stream = False
          handler(self, m)
          return True
    return False

  def process_line(self, line):
    """Processes a single line of output.

    Returns true if the line appears to be part of an instrumentation status
    message, False otherwise."""
    if self._process_instrumentation_line(line):
      return True

    if self._multiline_stream:
      self._current_stream.append(line)
      return True

    return False

  def process_text(self, text):
    """Processes an block of text."""
    try:
      for line in text.splitlines():
        self.process_line(line)
    except:
      print text
      raise

  @property
  def run_completed_cleanly(self):
    """True if the instrumentation run completed cleanly."""
    return self._suite_code is not None

  @property
  def output_recognized(self):
    """True if the output appears to contain the key messages expected from
    performing an "am instrument -r" command to run tests.

    This will be false until the first such messages are observed."""
    return self._recognized

  @property
  def run_message(self):
    """The text message printed summarizing the suite run."""
    return self._suite_message

  @property
  def run_passed_cleanly(self):
    """True if the instrumentation run had no errors."""
    return self._suite_code == ATFInstrumentationResultParser._RESULT_OK

  @property
  def test_methods_total(self):
    """The total number of test methods."""
    return self._tests_total

  @property
  def test_methods_passed(self):
    """The total number of passing test methods."""
    return self._tests_passed

  @property
  def test_methods_failed(self):
    """The total number of failing test methods."""
    return self._tests_failed

  @property
  def test_method_results(self):
    """The map of test names to results for all tests that ran.

    See TestMethodResult for the structure used for those
    results."""
    return self._test_fqn_to_result_map.copy()
