#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs multiple APKs and indicates how many succeed or fail."""

import argparse
import collections
import logging
import os
import re
import subprocess
import sys
import time

import build_common
from build_options import OPTIONS
from util import concurrent
from util import launch_chrome_util
from util import output_handler
from util import remote_executor


_OUT_DIR = 'out/test_apks_boot'

_FAILED_RE = re.compile(r'\[\s+FAILED\s+\]\n')
_FATAL_ALOG_RE = re.compile(r'F/\w+:')
_NDK_CRASH_RE = re.compile(r'F/libndk_translation: ')
_NDK_USED_RE = re.compile(r'I/libndk_translation: LoadLibrary: ')
_PASSED_RE = re.compile(r'\[\s+PASSED\s+\]\n')
_TIMEOUT_RE = re.compile(r'\[\s+TIMEOUT\s+\]\n')

# We clasify exit reason into the following 7 reasons.
_EXIT_CRASH = 'CRASH'
_EXIT_EXCEPTION = 'EXCEPTION'
_EXIT_FATAL = 'FATAL'
_EXIT_NDK_CRASH = 'NDK_CRASH'
_EXIT_PASSED = 'PASSED'
_EXIT_SHUTDOWN = 'SHUTDOWN'
_EXIT_TIMEOUT = 'TIMEOUT'
_EXIT_UNKNOWN = 'UNKNOWN'

# To make the order of outputs consistent.
_EXIT_REASONS = [
    _EXIT_PASSED, _EXIT_EXCEPTION, _EXIT_TIMEOUT, _EXIT_SHUTDOWN, _EXIT_CRASH,
    _EXIT_FATAL, _EXIT_NDK_CRASH, _EXIT_UNKNOWN
]

# When one of these lines is found, the detection code of Java exception is
# disabled until an empty line is found.
_KNOWN_JAVA_ERROR_LINES = [
    # TODO(crbug.com/341227): Remove this.
    r'W/InputMethodUtils: NameNotFoundException: com.android.inputmethod.latin',
    # TODO(crbug.com/346144): Remove this.
    r'java.io.FileNotFoundException: /data/system/sync/pending.xml'
]


def _make_line_handler(regex):
  return lambda line: bool(regex.search(line))


_CRASH_LINE_HANDLER = output_handler.is_crash_line
_EXCEPTION_LINE_HANDLER = output_handler.is_java_exception_line
_FAILED_LINE_HANDLER = _make_line_handler(_FAILED_RE)
_FATAL_ALOG_LINE_HANDLER = _make_line_handler(_FATAL_ALOG_RE)
_NDK_CRASH_LINE_HANDLER = _make_line_handler(_NDK_CRASH_RE)
_NDK_USED_LINE_HANDLER = _make_line_handler(_NDK_USED_RE)
_PASSED_LINE_HANDLER = _make_line_handler(_PASSED_RE)
_SHUTDOWN_LINE_HANDLER = output_handler.is_abnormal_exit_line
_TIMEOUT_LINE_HANDLER = _make_line_handler(_TIMEOUT_RE)


class ApkRunner(object):
  def __init__(self, apk, args):
    self._apk = apk
    self._args = args
    self._name = os.path.basename(self._apk)
    self._exit_reason = None
    self._java_exception_check_enabled = True

  def get_name(self):
    return self._name

  def get_exit_reason(self):
    return self._exit_reason

  def get_elapsed_secs(self):
    return self._elapsed_secs

  def has_ndk(self):
    return self._has_ndk

  def run(self):
    start_time = time.time()
    self._run_test()
    self._elapsed_secs = time.time() - start_time
    self._store_output()
    self._parse_output()
    self._show_result()

  def _run_test(self):
    args = launch_chrome_util.get_launch_chrome_command([
        'perftest',
        '--crx-name-override=test_apks_boot-' + self._name,
        '--minimum-lifetime=%d' % self._args.minimum_lifetime,
        '--minimum-steady=%d' % self._args.minimum_steady,
        '--noninja',
        '--stderr-log=I',
        '--timeout=%d' % self._args.timeout,
        '--use-temporary-data-dirs',
        '--verbose',
    ])
    args.extend(self._args.launch_chrome_opts)
    args.append(self._apk)

    remote_executor.copy_remote_arguments(self._args, args)
    proc = subprocess.Popen(args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    self._output = proc.communicate()[0]
    if self._args.remote:
      # Normalize the output because the output contains carriage returns when
      # launching chrome remotely via SSH.
      self._output = self._output.replace('\r\n', '\n')

  def _store_output(self):
    with open(os.path.join(_OUT_DIR, self._name + '.log'), 'w') as f:
      f.write(self._output)

  @staticmethod
  def _search_lines(search_lines, line):
    return any(re.search(search_line, line) for search_line in search_lines)

  def _check_known_errors(self, line):
    # Disable Java exception check until an empty line is found, which
    # indicates the end of the exception stack trace.
    if ApkRunner._search_lines(_KNOWN_JAVA_ERROR_LINES, line):
      self._java_exception_check_enabled = False
    if not line:
      self._java_exception_check_enabled = True

  def _parse_lines(self, lines, line_handler, reason):
    for line in lines:
      if reason == _EXIT_EXCEPTION:
        if not self._args.show_known_java_exceptions:
          self._check_known_errors(line)
        if not self._java_exception_check_enabled:
          continue
      if not line_handler(line):
        continue
      return True
    return False

  def _parse_output(self):
    self._has_ndk = _NDK_USED_RE.search(self._output)
    lines = self._output.splitlines(True)
    for line_handler, reason, msg in (
        (_NDK_CRASH_LINE_HANDLER, _EXIT_NDK_CRASH, None),
        (_FATAL_ALOG_LINE_HANDLER, _EXIT_FATAL, None),
        (_SHUTDOWN_LINE_HANDLER, _EXIT_SHUTDOWN, None),
        (_CRASH_LINE_HANDLER, _EXIT_CRASH, None),
        (_TIMEOUT_LINE_HANDLER, _EXIT_TIMEOUT, None),
        (_EXCEPTION_LINE_HANDLER, _EXIT_EXCEPTION, None),
        (_FAILED_LINE_HANDLER, _EXIT_UNKNOWN,
         # Output with a FAILED message should be classified into one
         # of the above failure reasons. If you see this message, it
         # means someone modified a case for which launch_chrome shows
         # FAILED but did not modify this script so this script is not
         # consistent with launch_chrome.
         'FAILED without specific reasons'),
        (_PASSED_LINE_HANDLER, _EXIT_PASSED, None)):
      if self._parse_lines(lines, line_handler, reason):
        if msg:
          logging.error('%s: %s' % (msg, self._name))
        self._exit_reason = reason
        return
    self._exit_reason = _EXIT_UNKNOWN

  def _show_result(self):
    ndk = ' (NDK)' if self.has_ndk() else ''
    # Note that we should use sys.stdout.write instead of print
    # statement as print is not atomic and we run APKs in parallel.
    sys.stdout.write('%s%s: %s [%.3fs]\n' % (self.get_name(),
                                             ndk,
                                             self.get_exit_reason(),
                                             self.get_elapsed_secs()))
    sys.stdout.flush()


def _create_result_categories(results):
  categories = []
  no_ndk_results = filter(lambda r: not r.has_ndk(), results)
  if no_ndk_results:
    categories.append(('Non NDK apps', no_ndk_results))
  ndk_results = filter(lambda r: r.has_ndk(), results)
  if ndk_results:
    categories.append(('NDK apps', ndk_results))
  categories.append(('All apps', results))
  return categories


def _show_stats(all_results):
  for category, results in _create_result_categories(all_results):
    num_results = len(results)
    sys.stdout.write('=== %s %d ===\n' % (category, num_results))
    counts = {}
    for result in results:
      reason = result.get_exit_reason()
      counts[reason] = counts.get(reason, 0) + 1

    for reason in _EXIT_REASONS:
      if reason not in counts:
        continue
      count = counts[reason]
      sys.stdout.write('%s %d (%d%%)\n' %
                       (reason, count, count * 100 / num_results))
    sys.stdout.write('\n')


def _output_tsv(all_results, tsv_file):
  results = sorted(all_results, key=lambda result: result.get_name())
  with open(tsv_file, 'w') as f:
    for result in results:
      f.write('%s\t%s\t%s\n' % (result.get_name(),
                                'YES' if result.has_ndk() else 'NO',
                                result.get_exit_reason()))


def _test_apks_boot(args):
  apk_runners = [ApkRunner(apk, args) for apk in args.apks]

  # Name duplication check.
  name_map = collections.defaultdict(int)
  for apk_runner in apk_runners:
    name_map[apk_runner.get_name()] += 1
  duplicated_name = [name for name, count in name_map.iteritems() if count > 1]
  if duplicated_name:
    raise Exception('The same apk is specified multiple times: %s' %
                    str(duplicated_name))

  # Run tests in parallel.
  with concurrent.ThreadPoolExecutor(
      max_workers=args.jobs, daemon=True) as executor:
    for apk_runner in apk_runners:
      executor.submit(apk_runner.run)
  return apk_runners


def main():
  description = ('Runs multiple APKs and indicates how many succeed or '
                 'fail and with what failure modes.')
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('-j', '--jobs', metavar='N', default=1, type=int,
                      help='Run N tests at once.')
  parser.add_argument('--launch-chrome-opt', action='append', default=[],
                      dest='launch_chrome_opts', metavar='OPTIONS',
                      help=('An Option to pass on to launch_chrome. Repeat as '
                            'needed for any options to pass on.'))
  parser.add_argument('--minimum-lifetime', type=int, default=0,
                      metavar='<T>', help='This flag will be passed to '
                      'launch_chrome to control the behavior after onResume. '
                      'This requires the application to continue running T '
                      'seconds.')
  parser.add_argument('--minimum-steady', type=int, default=0,
                      metavar='<T>', help='This flag will be passed to '
                      'launch_chrome to control the behavior after onResume. '
                      'This requires the application to continue running T '
                      'seconds with no output.')
  parser.add_argument('--noninja', action='store_false',
                      default=True, dest='run_ninja',
                      help='Do not run ninja before running any tests.')
  parser.add_argument('--timeout', metavar='T', default=60, type=int,
                      help='Timeout value for onResume. Once onResume '
                      'fires, --minimum-lifetime and --minimum-steady '
                      'determine when the application is considered '
                      'successfully running.')
  parser.add_argument('--show-known-java-exceptions', action='store_true',
                      help='Show the known Java exceptions if this flag '
                      'is specified.')
  parser.add_argument('--tsv', metavar='TSV', help='Output results in TSV to '
                      'the file specified by this argument.')
  parser.add_argument('apks', metavar='apk', nargs='*',
                      help='Filenames of APKs.')
  remote_executor.add_remote_arguments(parser)

  args = parser.parse_args()

  OPTIONS.parse_configure_file()

  if args.run_ninja:
    build_common.run_ninja()

  if not os.path.exists(_OUT_DIR):
    os.mkdir(_OUT_DIR)

  sys.stdout.write('=== Results ===\n')
  results = _test_apks_boot(args)
  sys.stdout.write('\n')
  _show_stats(results)
  if args.tsv:
    _output_tsv(results, args.tsv)

if __name__ == '__main__':
  sys.exit(main())
