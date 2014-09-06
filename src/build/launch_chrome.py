#!/usr/bin/python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import atexit
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urlparse

import build_common
import filtered_subprocess
import launch_chrome_options
import prep_launch_chrome
import toolchain
import util.statistics
from build_options import OPTIONS
from util import debug
from util import gdb_util
from util import nonblocking_io
from util import platform_util
from util import remote_executor
from util.minidump_filter import MinidumpFilter
from util.output_handler import ATFTestHandler
from util.output_handler import ArcStraceFilter
from util.output_handler import CrashAddressFilter
from util.output_handler import OutputDumper
from util.output_handler import PerfTestHandler


_ROOT_DIR = build_common.get_arc_root()

_CHROME_KILL_DELAY = 0.1

_CHROME_KILL_TIMEOUT = 10

_CHROME_PID_PATH = None

_PERF_TOOL = 'perf'

_USER_DATA_DIR = None  # Will be set after we parse the commandline flags.


# Caution: The feature to kill the running chrome has race condition, that this
# may kill unrelated process. The file can be rewritten at anytime, so there
# is no simpler way to guarantee that the pid read from the file is reliable.
# Note that technically we should be able to lock the file, but python does
# not provide portable implementation.
def _read_chrome_pid_file():
  if not os.path.exists(_CHROME_PID_PATH):
    return None

  with open(_CHROME_PID_PATH) as pid_file:
    lines = pid_file.readlines()
  if not lines:
    logging.error('chrome.pid is empty.')
    return None
  try:
    return int(lines[0])
  except ValueError:
    logging.error('Invalid content of chrome.pid: ' + lines[0])
    return None


def _kill_running_chrome():
  pid = _read_chrome_pid_file()
  if pid is None:
    return

  try:
    if OPTIONS.is_nacl_build():
      # For now use sigkill, as NaCl's debug stub seems to cause sigterm to
      # be ignored.
      os.kill(pid, signal.SIGKILL)
    else:
      os.kill(pid, signal.SIGTERM)

    # Unfortunately, there is no convenient API to wait subprocess's
    # termination with timeout. So, here we just poll it.
    wait_time_limit = time.time() + _CHROME_KILL_TIMEOUT
    while True:
      retpid, status = os.waitpid(pid, os.WNOHANG)
      if retpid:
        break
      now = time.time()
      if now > wait_time_limit:
        logging.error('Terminating Chrome is timed out: %d', pid)
        break
      time.sleep(min(_CHROME_KILL_DELAY, wait_time_limit - now))
  except OSError:
    # Here we ignore the OS error. The process may have been terminated somehow
    # by external reason, while the file still exists on the file system.
    pass

  _remove_chrome_pid_file(pid)


def _remove_chrome_pid_file(pid):
  read_pid = _read_chrome_pid_file()
  if read_pid == pid:
    try:
      os.remove(_CHROME_PID_PATH)
    except OSError:
      # The file may already be removed due to timing issue. Ignore the error.
      pass


def _prepare_chrome_user_data_dir(parsed_args):
  global _USER_DATA_DIR
  if parsed_args.use_temporary_data_dirs:
    _USER_DATA_DIR = tempfile.mkdtemp(
        prefix=build_common.CHROME_USER_DATA_DIR_PREFIX + '-')
    atexit.register(lambda: build_common.rmtree_with_retries(_USER_DATA_DIR))
  elif parsed_args.user_data_dir:
    _USER_DATA_DIR = parsed_args.user_data_dir
  else:
    _USER_DATA_DIR = build_common.get_chrome_default_user_data_dir()


class StartupStats:
  STAT_VARS = ['pre_plugin_time_ms',
               'pre_embed_time_ms',
               'plugin_load_time_ms',
               'on_resume_time_ms',
               'app_virt_mem',
               'app_res_mem']

  def __init__(self, num_runs=1):
    self.num_runs = num_runs
    for name in StartupStats.STAT_VARS:
      setattr(self, name, None)

    self.pre_plugin_perf_message_pattern = re.compile(
        r'W/libplugin.*Time spent before plugin: (\d+)ms = (\d+)ms \+ (\d+)ms')
    self.start_message_pattern = re.compile(
        (r'\d+\.\d+s \+ (\d+\.\d+)s = \d+\.\d+s '
         '\(\+(\d+)M virt\, \+(\d+)M res.*\): '
         'Activity onResume .*'))

  def check(self):
    if not self.is_complete():
      raise Exception('Not all stats were collected')

  def is_complete(self):
    if any(getattr(self, num) is None for num in StartupStats.STAT_VARS):
      return False
    return True

  def parse_pre_plugin_perf_message(self, line):
    match = self.pre_plugin_perf_message_pattern.match(line)
    if match:
      print line
      self.pre_plugin_time_ms = int(match.group(1))
      self.pre_embed_time_ms = int(match.group(2))
      self.plugin_load_time_ms = int(match.group(3))
      return True
    return False

  def parse_app_start_message(self, line):
    if self.on_resume_time_ms is not None:
      return  # Ignore subsequent messages
    match = self.start_message_pattern.match(line)
    if match:
      self.on_resume_time_ms = int(float(match.group(1)) * 1000)
      self.app_virt_mem = int(match.group(2))
      self.app_res_mem = int(match.group(3))
      return True
    return False

  def PrintDetailedStats(self):
    rawstats = {key: [] for key in ['boot_time_ms'] + StartupStats.STAT_VARS}
    for num in ['boot_time_ms'] + StartupStats.STAT_VARS:
      for run in getattr(self, 'raw'):
        rawstats[num].append(getattr(run, num))
      unit = 'ms' if num.endswith('_ms') else 'MB'
      val = getattr(self, num)
      p90 = getattr(self, num + '_90')
      print ('VPERF=%s: %.2f%s 90%%=%.2f' %
             (num, val, unit, p90))
    print ('VRAWPERF=%s' % rawstats)

  def Print(self):
    # Note: since each value is the median for each data set, they are not
    # guaranteed to add up.
    print ('\nPERF=boot:%dms (preEmbed:%dms + pluginLoad:%dms + onResume:%dms),'
           '\n     virt:%dMB, res:%dMB, runs:%d\n' % (
               self.boot_time_ms,
               self.pre_embed_time_ms,
               self.plugin_load_time_ms,
               self.on_resume_time_ms,
               self.app_virt_mem,
               self.app_res_mem,
               self.num_runs))

  @staticmethod
  def compute_stats(stat_list):
    # Skip incomplete stats (probably crashed during this run).  We collect
    # enough runs to make up for an occasional missed run.
    stat_list = filter(lambda s: s.is_complete(), stat_list)
    for s in stat_list:
      s.boot_time_ms = s.pre_plugin_time_ms + s.on_resume_time_ms

    result = StartupStats(len(stat_list))
    setattr(result, 'raw', stat_list)
    for num in ['boot_time_ms'] + StartupStats.STAT_VARS:
      values = [getattr(s, num) for s in stat_list]
      percentiles = util.statistics.compute_percentiles(values, (50, 90))

      # Report median and 90th percentile.
      setattr(result, num, percentiles[0])
      setattr(result, num + '_90', percentiles[1])
    return result


def set_environment_for_chrome():
  # Prevent GTK from attempting to move the menu bar, which prints many warnings
  # about undefined symbol "menu_proxy_module_load"
  if 'UBUNTU_MENUPROXY' in os.environ:
    del os.environ['UBUNTU_MENUPROXY']

  # TODO(https://code.google.com/p/nativeclient/issues/detail?id=1981):
  # Remove this TMPDIR setup.
  tmp = tempfile.mkdtemp()
  assert(tmp != '/')
  atexit.register(lambda: build_common.rmtree_with_retries(tmp))
  os.environ['TMPDIR'] = tmp


def _run_chrome_iterations(parsed_args):
  if not parsed_args.no_cache_warming:
    stats = StartupStats()
    _run_chrome(parsed_args, stats, cache_warming=True)
    if parsed_args.mode == 'perftest':
      total = (stats.pre_embed_time_ms + stats.plugin_load_time_ms +
               stats.on_resume_time_ms)
      print 'WARM-UP %d %d %d %d' % (total,
                                     stats.pre_embed_time_ms,
                                     stats.plugin_load_time_ms,
                                     stats.on_resume_time_ms)

  if parsed_args.iterations > 0:
    stat_list = []
    for i in xrange(parsed_args.iterations):
      stats = StartupStats()
      sys.stderr.write('\nStarting Chrome, test run #%s\n' %
                       (len(stat_list) + 1))
      _run_chrome(parsed_args, stats)
      stat_list.append(stats)
    stats = StartupStats.compute_stats(stat_list)
    if stats.num_runs:
      stats.PrintDetailedStats()
    stats.Print()


def _check_apk_existence(parsed_args):
  for apk_path in parsed_args.apk_path_list:
    is_file = (parsed_args.mode != 'driveby' or
               urlparse.urlparse(apk_path).scheme == '')
    if is_file and not os.path.exists(apk_path):
      raise Exception('APK does not exist:' + apk_path)


def _check_crx_existence(parsed_args):
  if (not parsed_args.build_crx and
      parsed_args.mode != 'driveby' and
      not os.path.exists(parsed_args.arc_data_dir)):
    raise Exception('--nocrxbuild is used but CRX does not exist in %s.\n'
                    'Try launching chrome without --nocrxbuild in order to '
                    'rebuild the CRX.' % parsed_args.arc_data_dir)


def _get_chrome_path(parsed_args):
  if parsed_args.chrome_binary:
    return parsed_args.chrome_binary
  else:
    return remote_executor.get_chrome_exe_path()


def _setup_sigterm_handler():
  # We much rely on atexit module in this script. Some other scripts, such as
  # run_integration_tests, send the SIGTERM to let this script know to be
  # graceful shutdown. So we translate it to sys.exit, which is just raising an
  # SystemExit so that functions registered to atexit should work properly.
  def sigterm_handler(signum, frame):
    debug.write_frames(sys.stderr)
    sys.exit(1)
  signal.signal(signal.SIGTERM, sigterm_handler)


def main():
  _setup_sigterm_handler()

  OPTIONS.parse_configure_file()

  parsed_args = launch_chrome_options.parse_args(sys.argv)

  _prepare_chrome_user_data_dir(parsed_args)
  global _CHROME_PID_PATH
  _CHROME_PID_PATH = os.path.join(_USER_DATA_DIR, 'chrome.pid')

  # If there is an X server at :0.0 and GPU is enabled, set it as the
  # current display.
  if parsed_args.display:
    os.environ['DISPLAY'] = parsed_args.display

  os.chdir(_ROOT_DIR)

  if not parsed_args.remote:
    _kill_running_chrome()

  if parsed_args.run_ninja:
    build_common.run_ninja()

  ld_library_path = os.environ.get('LD_LIBRARY_PATH')
  lib_paths = ld_library_path.split(':') if ld_library_path else []
  lib_paths.append(build_common.get_load_library_path())
  # Add the directory of the chrome binary so that .so files in the directory
  # can be loaded. This is needed for loading libudev.so.0.
  # TODO(crbug.com/375609): Remove the hack once it becomes no longer needed.
  lib_paths.append(os.path.dirname(_get_chrome_path(parsed_args)))
  os.environ['LD_LIBRARY_PATH'] = ':'.join(lib_paths)
  set_environment_for_chrome()

  if not platform_util.is_running_on_remote_host():
    _check_apk_existence(parsed_args)

  # Do not build crx for drive by mode.
  # TODO(crbug.com/326724): Transfer args to metadata in driveby mode.
  if parsed_args.mode != 'driveby':
    if not platform_util.is_running_on_remote_host():
      prep_launch_chrome.prepare_crx(parsed_args)
    prep_launch_chrome.remove_crx_at_exit_if_needed(parsed_args)

  if parsed_args.remote:
    remote_executor.launch_remote_chrome(parsed_args, sys.argv[1:])
  else:
    platform_util.assert_machine(OPTIONS.target())
    _check_crx_existence(parsed_args)
    _run_chrome_iterations(parsed_args)

  return 0


class ChromeProcess(filtered_subprocess.Popen):
  def __init__(self, params):
    if not platform_util.is_running_on_cygwin():
      super(ChromeProcess, self).__init__(params)
      self._tail_stdout_process = None
      self._tail_stderr_process = None
      return

    # To launch on Cygwin, stdout and stderr for NaCl is not yet supported.
    # Instead, here we redirect them to each file, and use "tail -f".
    # See also remote_windows_executor.py for more details.
    # We also stdout and stderr of Chrome to temporary files and pass them to
    # tail so that the outputs from both Chrome and NaCl are filtered by the
    # output handler.
    chrome_stdout = build_common.create_tempfile_deleted_at_exit(
        prefix='Chrome-stdout')
    chrome_stderr = build_common.create_tempfile_deleted_at_exit(
        prefix='Chrome-stderr')
    super(ChromeProcess, self).__init__(params,
                                        stdout=chrome_stdout,
                                        stderr=chrome_stderr)
    nacl_logfile_path = os.environ['NACLLOG']
    nacl_stdout_path = os.environ['NACL_EXE_STDOUT']
    nacl_stderr_path = os.environ['NACL_EXE_STDERR']

    # Poll until all files are created.
    while (not os.path.exists(nacl_logfile_path) or
           not os.path.exists(nacl_stdout_path) or
           not os.path.exists(nacl_stderr_path)):
      time.sleep(0.1)
    self._tail_stdout_process = subprocess.Popen(
        ['tail', '-f', chrome_stdout.name, nacl_stdout_path, '-n', '+1'],
        stdout=subprocess.PIPE)
    self._tail_stderr_process = subprocess.Popen(
        ['tail', '-f', chrome_stderr.name, nacl_stderr_path, '-n', '+1'],
        stdout=subprocess.PIPE)
    self.stdout = nonblocking_io.LineReader(self._tail_stdout_process.stdout)
    self.stderr = nonblocking_io.LineReader(self._tail_stderr_process.stdout)

  def terminate_tail_processes(self):
    if self._tail_stdout_process and self._tail_stdout_process.poll() is None:
      self._tail_stdout_process.terminate()
      self._tail_stdout_process = None
    if self._tail_stderr_process and self._tail_stderr_process.poll() is None:
      self._tail_stderr_process.terminate()
      self._tail_stderr_process = None

  def kill_tail_processes(self):
    if self._tail_stdout_process and self._tail_stdout_process.poll() is None:
      self._tail_stdout_process.kill()
      self._tail_stdout_process = None
    if self._tail_stderr_process and self._tail_stderr_process.poll() is None:
      self._tail_stderr_process.kill()
      self._tail_stderr_process = None

  def terminate(self):
    self.terminate_tail_processes()
    super(ChromeProcess, self).terminate()

  def kill(self):
    self.kill_tail_processes()
    super(ChromeProcess, self).kill()

  def get_error_level(self):
    error_level = self.returncode
    # Chrome exits with -signal.SIGTERM (-15) on Mac and Cygwin when it
    # receives SIGTERM, so -signal.SIGTERM (-15) is an expected exit code.
    # Although Chrome on Linux handles SIGTERM and exits with 0, we treat it
    # in the same way as other platforms for consistency.
    if error_level == -signal.SIGTERM:
      error_level = 0
    # Sometimes Chrome is not terminated by SIGTERM.
    # In such a case, we send SIGKILL to kill the process, so -signal.SIGKILL
    # (-9) is also expected exit code.
    if error_level == -signal.SIGKILL:
      error_level = 0
    return error_level


def _compute_chrome_plugin_params(parsed_args):
  params = []
  extensions = [
      remote_executor.resolve_path(build_common.get_runtime_out_dir()),
      remote_executor.resolve_path(build_common.get_handler_dir())]
  params.append('--load-extension=' + ','.join(extensions))

  params.append(
      '--user-data-dir=' + remote_executor.resolve_path(_USER_DATA_DIR))

  # Not all targets can use nonsfi mode (even with the whitelist).
  if OPTIONS.is_bare_metal_build():
    params.append('--enable-nacl-nonsfi-mode')

  return params


def _is_no_sandbox_needed(parsed_args):
  if parsed_args.disable_nacl_sandbox:
    return True

  # Official Chrome needs setuid + root ownership to run.  --no-sandbox
  # bypasses that.
  if OPTIONS.is_official_chrome():
    return True

  # In some cases, --no-sandbox is needed to work gdb properly.
  if gdb_util.is_no_sandbox_needed(parsed_args.gdb):
    return True

  # Set --no-sandbox on Mac for now because ARC apps crash on Mac Chromium
  # without the flag.
  # TODO(crbug.com/332785): Investigate the cause of crash and remove the flag
  # if possible.
  if platform_util.is_running_on_mac():
    return True

  return False


def _compute_chrome_sandbox_params(parsed_args):
  params = []
  if _is_no_sandbox_needed(parsed_args):
    params.append('--no-sandbox')
    if OPTIONS.is_bare_metal_build():
      # Non-SFI NaCl helper, which heavily depends on seccomp-bpf,
      # does not start without seccomp sandbox initialized unless we
      # specify this flag explicitly.
      params.append('--nacl-dangerous-no-sandbox-nonsfi')

  # Environment variables to pass through to nacl_helper.
  passthrough_env_vars = []

  if OPTIONS.is_nacl_build() and parsed_args.disable_nacl_sandbox:
    os.environ['NACL_DANGEROUS_ENABLE_FILE_ACCESS'] = '1'
    passthrough_env_vars.append('NACL_DANGEROUS_ENABLE_FILE_ACCESS')
  if OPTIONS.is_nacl_build() and parsed_args.enable_nacl_list_mappings:
    os.environ['NACL_DANGEROUS_ENABLE_LIST_MAPPINGS'] = '1'
    passthrough_env_vars.append('NACL_DANGEROUS_ENABLE_LIST_MAPPINGS')
  if passthrough_env_vars:
    os.environ['NACL_ENV_PASSTHROUGH'] = ','.join(passthrough_env_vars)
  return params


def _compute_chrome_graphics_params(parsed_args):
  params = []
  params.append('--disable-gl-error-limit')

  # Always use the compositor thread. All desktop Chrome except Linux already
  # use it.
  params.append('--enable-threaded-compositing')

  if parsed_args.enable_osmesa:
    params.append('--use-gl=osmesa')

  # The NVidia GPU on buildbot is blacklisted due to unstableness of graphic
  # driver even there is secondary Matrox GPU(http://crbug.com/145600). It
  # happens with low memory but seems safe for buildbot. So passing
  # ignore-gpu-blacklist to be able to use hardware acceleration.
  if OPTIONS.is_hw_renderer():
    params.append('--ignore-gpu-blacklist')

  return params


def _compute_chrome_debugging_params(parsed_args):
  params = []

  # This reduce one step necessary to enable filesystem inspector.
  params.append('--enable-devtools-experiments')

  if OPTIONS.is_nacl_build() and 'plugin' in parsed_args.gdb:
    params.append('--enable-nacl-debug')
    params.append('--wait-for-debugger-children')

  if len(parsed_args.gdb):
    params.append('--disable-hang-monitor')

  if 'gpu' in parsed_args.gdb:
    params.append('--gpu-startup-dialog')
    params.append('--disable-gpu-watchdog')

  if 'renderer' in parsed_args.gdb:
    params.append('--renderer-startup-dialog')

  if parsed_args.enable_fake_video_source:
    params.append('--use-fake-device-for-media-stream')

  return params


def _compute_chrome_diagnostic_params(parsed_args):
  if OPTIONS.is_nacl_build():
    opt = '--nacl-loader-cmd-prefix'
  else:
    opt = '--ppapi-plugin-launcher'

  params = []
  # Loading NaCl module gets stuck if --enable-logging=stderr is specified
  # together with --perfstartup.
  # TODO(crbug.com/276891): Investigate the root cause of the issue and fix it.
  if OPTIONS.is_nacl_build() and parsed_args.perfstartup:
    params.append('--enable-logging')
  else:
    params.append('--enable-logging=stderr')
  params.append('--log-level=0')

  if parsed_args.tracestartup > 0:
    params.append('--trace-startup')
    params.append('--trace-startup-duration=%d' % parsed_args.tracestartup)

  if parsed_args.perfstartup:
    params.append('%s=timeout -s INT %s %s record -gf -o out/perf.data' %
                  (opt, parsed_args.perfstartup, _PERF_TOOL))

  return params


def _compute_chrome_performance_test_params(unused_parsed_args):
  """Add params that are necessary for stable perftest result."""
  params = []

  # Skip First Run tasks, whether or not it's actually the First Run.
  params.append('--no-first-run')

  # Disable default component extensions with background pages - useful for
  # performance tests where these pages may interfere with perf results.
  params.append('--disable-component-extensions-with-background-pages')

  # Enable the recording of metrics reports but disable reporting. In contrast
  # to kDisableMetrics, this executes all the code that a normal client would
  # use for reporting, except the report is dropped rather than sent to the
  # server. This is useful for finding issues in the metrics code during UI and
  # performance tests.
  params.append('--metrics-recording-only')

  # Disable several subsystems which run network requests in the background.
  # This is for use when doing network performance testing to avoid noise in the
  # measurements.
  params.append('--disable-background-networking')

  # They are copied from
  #  ppapi/native_client/tools/browser_tester/browsertester/browserlauncher.py
  # These features could be a source of non-determinism too.
  params.append('--disable-default-apps')
  params.append('--disable-preconnect')
  params.append('--disable-sync')
  params.append('--disable-web-resources')
  params.append('--dns-prefetch-disable')
  params.append('--no-default-browser-check')
  params.append('--safebrowsing-disable-auto-update')

  return params


def _compute_chrome_params(parsed_args):
  chrome_path = _get_chrome_path(parsed_args)
  params = [chrome_path]

  if parsed_args.mode == 'perftest':
    # Do not show the New Tab Page because showing NTP during perftest makes the
    # benchmark score look unnecessarily bad.
    # TODO(crbug.com/315356): Remove the IF once 315356 is fixed.
    params.append('about:blank')

  if parsed_args.mode != 'run':
    # Append flags for performance measurement in the modes other than run
    # mode to stabilize integration tests and perf score. Do not append these
    # flags in run mode because apps that depend on component extensions
    # (e.g. Files.app) won't work with these flags.
    params.extend(_compute_chrome_performance_test_params(parsed_args))

  if parsed_args.mode == 'perftest' or parsed_args.mode == 'atftest':
    # Make the window size small on Goobuntu so that it does not cover the whole
    # desktop during perftest/integration_test.
    params.append('--window-size=500,500')

  if parsed_args.lang:
    params.append('--lang=' + parsed_args.lang)
    # LANGUAGE takes priority over --lang option in Linux.
    os.environ['LANGUAGE'] = parsed_args.lang
    # In Mac, there is no handy way to change the locale.
    if sys.platform == 'darwin':
      print '\nWARNING: --lang is not supported in Mac.'

  params.extend(_compute_chrome_plugin_params(parsed_args))
  params.extend(_compute_chrome_sandbox_params(parsed_args))
  params.extend(_compute_chrome_graphics_params(parsed_args))
  params.extend(_compute_chrome_debugging_params(parsed_args))
  params.extend(_compute_chrome_diagnostic_params(parsed_args))
  remote_executor.maybe_extend_remote_host_chrome_params(parsed_args, params)

  if parsed_args.mode == 'driveby':
    params.append(remote_executor.resolve_path(parsed_args.apk_path_list[0]))
  else:
    params.append(
        '--load-and-launch-app=' +
        remote_executor.resolve_path(parsed_args.arc_data_dir))

  # This prevents Chrome to add icon to Gnome panel, which current leaks memory.
  # See http://crbug.com/341724 for details.
  params.append('--disable-background-mode')

  if parsed_args.chrome_args:
    params.extend(parsed_args.chrome_args)

  return params


def _should_timeouts_be_used(parsed_args):
  if parsed_args.jdb_port or parsed_args.gdb:
    # Do not apply a timeout if debugging
    return False

  if parsed_args.mode not in ('atftest', 'perftest'):
    return False

  return True


def _select_chrome_timeout(parsed_args):
  if not _should_timeouts_be_used(parsed_args):
    return None
  return parsed_args.timeout


def _select_chrome_output_timeout(parsed_args):
  if not _should_timeouts_be_used(parsed_args):
    return None
  return parsed_args.output_timeout


def _select_output_handler(parsed_args, stats, chrome_process, **kwargs):
  if parsed_args.mode == 'atftest':
    output_handler = ATFTestHandler()
  elif parsed_args.mode == 'perftest':
    output_handler = PerfTestHandler(parsed_args, stats, chrome_process,
                                     **kwargs)
  else:
    output_handler = OutputDumper(parsed_args)

  if 'gpu' in parsed_args.gdb or 'renderer' in parsed_args.gdb:
    output_handler = gdb_util.GdbHandlerAdapter(
        output_handler, parsed_args.gdb, parsed_args.gdb_type)

  if (parsed_args.enable_arc_strace and
      parsed_args.arc_strace_output != 'stderr'):
    output_handler = ArcStraceFilter(output_handler,
                                     parsed_args.arc_strace_output)

  output_handler = CrashAddressFilter(output_handler)

  if (OPTIONS.is_crash_reporting_enabled() and
      not platform_util.is_running_on_remote_host()):
    output_handler = MinidumpFilter(output_handler)

  return output_handler


def _terminate_chrome(chrome):
  _remove_chrome_pid_file(chrome.pid)

  if chrome.poll() is not None:
    # The chrome process is already terminated.
    return

  if OPTIONS.is_nacl_build():
    # For now use sigkill, as NaCl's debug stub seems to cause sigterm to
    # be ignored.
    chrome.kill()
  else:
    chrome.terminate()

  # Unfortunately, there is no convenient API to wait subprocess's termination
  # with timeout. So, here we just poll it.
  wait_time_limit = time.time() + _CHROME_KILL_TIMEOUT
  while True:
    if chrome.poll() is not None:
      break
    now = time.time()
    if now > wait_time_limit:
      break
    time.sleep(min(_CHROME_KILL_DELAY, wait_time_limit - now))


def _run_chrome(parsed_args, stats, **kwargs):
  if parsed_args.logcat is not None:
    # Using atexit for terminating subprocesses has timing issue.
    # There is (commonly very short) period between the subprocess creation and
    # registering the callback to atexit.register(). So, if some signal is sent
    # between them, atexit will not work well. However, it should cover most
    # cases.
    adb = subprocess.Popen(
        [toolchain.get_tool('host', 'adb'), 'logcat'] + parsed_args.logcat)
    atexit.register(lambda: adb.poll() is not None or adb.kill())

  params = _compute_chrome_params(parsed_args)
  gdb_util.create_or_remove_bare_metal_gdb_lock_file(parsed_args.gdb)

  # Similar to adb subprocess, using atexit has timing issue. See above comment
  # for the details.
  p = ChromeProcess(params)
  atexit.register(_terminate_chrome, p)

  gdb_util.maybe_launch_gdb(parsed_args.gdb, parsed_args.gdb_type, p.pid)

  # Write the PID to a file, so that other launch_chrome process sharing the
  # same user data can find the process. In common case, the file will be
  # removed by _terminate_chrome() defined above.
  build_common.makedirs_safely(_USER_DATA_DIR)
  with open(_CHROME_PID_PATH, 'w') as pid_file:
    pid_file.write('%d\n' % p.pid)

  chrome_timeout = _select_chrome_timeout(parsed_args)
  chrome_output_timeout = _select_chrome_output_timeout(parsed_args)
  output_handler = _select_output_handler(parsed_args, stats, p, **kwargs)

  # Wait for the process to finish or us to be interrupted.
  try:
    p.run_process_filtering_output(output_handler, timeout=chrome_timeout,
                                   output_timeout=chrome_output_timeout)
  except KeyboardInterrupt:
    sys.exit(1)

  if p.returncode:
    logging.error('Chrome is terminated with status code: %d', p.returncode)

  error_level = p.get_error_level()
  error_level = output_handler.get_error_level(error_level)
  if error_level != 0:
    sys.exit(error_level)


if __name__ == '__main__':
  sys.exit(main())
