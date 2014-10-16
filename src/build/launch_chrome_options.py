#!/usr/bin/python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Provides functions for parsing the options for launch_chrome.py and
# prep_launch_script.py.

import argparse
import json
import logging
import os
import re
import sys

from build_options import OPTIONS
from ninja_generator import ApkFromSdkNinjaGenerator
from util import launch_chrome_util
from util import remote_executor

# The values in _ALLOWED_* must be synchronized with _ALLOWED_VALUES in
# src/packaging/runtime/common.js.
_ALLOWED_FORMFACTORS = ['phone', 'tablet']

_ALLOWED_FORMFACTOR_MAPPING = {'p': 'phone', 't': 'tablet'}

_ALLOWED_NDK_ABIS = ['armeabi', 'armeabi-v7a']

_ALLOWED_ORIENTATIONS = ['landscape', 'portrait']

_ALLOWED_ORIENTATION_MAPPING = {'l': 'landscape', 'p': 'portrait'}

_ALLOWED_RESIZES = ['disabled', 'scale']

_ALLOWED_STDERR_LOGS = ['D', 'V', 'I', 'W', 'E', 'F', 'S']

_DATA_ROOTS_PATH = os.path.join('out', 'data_roots')

_DEFAULT_TIMEOUT = 60

_SYSTEM_CRX_NAME = 'system_mode.default'


def _parse_barewords(args, parsed_args):
  for i in range(0, len(args)):
    if re.match('.*\.apk', args[i]):
      if parsed_args.mode == 'driveby' and parsed_args.apk_path_list:
        raise Exception('More than one apk given in driveby mode')
      parsed_args.apk_path_list.append(args[i])
    else:
      raise Exception('Unrecognized arg "%s"' % args[i])
  return True


def _parse_mode_arguments(remaining_args, parsed_args):
  if not _parse_barewords(remaining_args, parsed_args):
    return False

  if not parsed_args.apk_path_list and parsed_args.mode != 'system':
    if parsed_args.mode == 'atftest':
      raise Exception('Must specify atftest test')
    parsed_args.apk_path_list = \
        [ApkFromSdkNinjaGenerator.get_install_path_for_module('HelloAndroid')]

  # TODO(crbug.com/308425): Currently, system mode CRX is generated in the
  # launch_chrome. But it should be generated in the build step.
  if not parsed_args.crx_name_override and parsed_args.mode == 'system':
    parsed_args.crx_name_override = _SYSTEM_CRX_NAME

  # The last APK listed is the one that is actually run. For consistency, use
  # it also for the path to the unpacked CRX.
  if parsed_args.mode != 'driveby':
    parsed_args.arc_data_dir = _get_arc_data_dir(parsed_args)

  return True


def _validate_mode_settings(parser, args):
  if args.mode == 'driveby':
    if not OPTIONS.is_nacl_build():
      parser.error('driveby mode works only with NaCl build')


def _parse_formfactor(value):
  if value in _ALLOWED_FORMFACTORS:
    return value
  elif value in _ALLOWED_FORMFACTOR_MAPPING.keys():
    return _ALLOWED_FORMFACTOR_MAPPING[value]
  raise argparse.ArgumentError('Invalid form-factor')


def _parse_gdb_targets(value):
  known_targets = ('plugin', 'gpu', 'renderer', 'browser')
  targets = []
  for t in value.split(','):
    if t in known_targets:
      targets.append(t)
    else:
      print 'discarding unknown gdb target:', t
  return targets


def _parse_orientation(value):
  if value in _ALLOWED_ORIENTATIONS:
    return value
  elif value in _ALLOWED_ORIENTATION_MAPPING.keys():
    return _ALLOWED_ORIENTATION_MAPPING[value]
  raise argparse.ArgumentError('Invalid orientation')


def _validate_perftest_settings(parser, args):
  if args.mode == 'perftest':
    if args.iterations < 1:
      args.iterations = 1
  else:
    if args.no_cache_warming:
      parser.error("--no-cache-warming only valid in 'perftest' mode")
    if args.iterations:
      parser.error("--iterations only valid in 'perftest' mode")
    if args.minimum_lifetime:
      parser.error("--minimum-lifetime only valid in 'perftest' mode")
    if args.minimum_steady:
      parser.error("--minimum-steady only valid in 'perftest' mode")


def _validate_system_settings(parser, args):
  if args.mode != 'system':
    return

  args.enable_adb = True

  if args.apk_path_list:
    parser.error("[path-to-apk]* is not valid in 'system' mode")


def _validate_gdb_type(parser, args):
  if args.gdb_type == 'wait':
    if len(args.gdb) != 1 or args.gdb[0] != 'plugin':
      parser.error('--gdb_type=wait works only with --gdb=plugin')


def _validate_remote_debug_settings(parser, args):
  if 'plugin' in args.gdb:
    if (args.nacl_helper_binary and
        not os.path.exists(args.nacl_helper_binary)):
      parser.error('The file specified by --nacl-helper-binary must exist '
                   'in your workstation.')
  else:
    if args.nacl_helper_binary:
      parser.error('--nacl-helper-binary can only be used with --gdb=plugin')


def _validate_debug_modes(parser, args):
  debug_modes = []
  if args.gdb:
    debug_modes.append('gdb')
  if args.perfstartup:
    debug_modes.append('perfstartup')
  if args.tracestartup:
    debug_modes.append('tracestartup')
  if len(debug_modes) > 1:
    parser.error("Cannot use more than 1 debug mode:" + str(debug_modes))

  _validate_gdb_type(parser, args)
  _validate_remote_debug_settings(parser, args)


def _validate_timeout(parser, args):
  if (args.timeout != _DEFAULT_TIMEOUT and
      args.mode not in ['perftest', 'atftest', 'system']):
    parser.error("--timeout  only valid in 'perftest' or 'atftest' mode")


def _validate_arc_strace(parser, args):
  if args.enable_arc_strace:
    if not OPTIONS.is_debug_code_enabled():
      parser.error("./configure --disable-debug-code is not compatible "
                   "with --enable-arc-strace")


def _setup_filterspec_from_args(args):
  if args.silent:
    args.stderr_log = 'S'
  if args.logcat is not None:
    args.stderr_log = 'S'
    args.enable_adb = True


def _resolve_perf_test_mode(args):
  if args.mode == 'perftest':
    # Use clean profile for performance test.
    args.use_temporary_data_dirs = True
    args.no_cache_warming = False
    if args.minimum_launch_delay is not None:
      return
    if args.remote:
      # Right after launching Chrome, the browser process is very busy doing its
      # own initialization and installing the ARC app to its disk. On Z620,
      # where disk is very fast and many CPU cores are available, the tasks
      # running in the browser process does not affect perftest score that much,
      # but on Chromebooks, especially Yoshi, it does. To make the perftest
      # score more realistic, add 1.5s wait to the onLaunched handler in
      # main.html.
      args.minimum_launch_delay = 1500  # in milliseconds.
    else:
      # Launch delay to allow dexopt to complete.
      args.minimum_launch_delay = 500  # in milliseconds.


def _get_arc_data_dir(parsed_args):
  if parsed_args.crx_name_override:
    # We use crx_name_override to isolate /mnt and /data of non pepper FS mode.
    crx_name = parsed_args.crx_name_override
  else:
    # Chrome does not like spaces in paths to CRXs to load.
    crx_name = os.path.splitext(os.path.basename(
        parsed_args.apk_path_list[-1]))[0]
  return os.path.join(_DATA_ROOTS_PATH, crx_name.replace(' ', '_'))


def _set_default_args(args):
  """Override for local developing if not specific."""
  if args.stderr_log is None:
    args.stderr_log = 'W'


def parse_args(argv):
  parser = argparse.ArgumentParser(
      prog='launch_chrome.py',
      fromfile_prefix_chars='@',
      usage='%(prog)s [options...] <command> [...]',
      description="""Commands:

  atftest [path-to-apk]*
      Starts Chrome, and launches the first set of tests found which target the
      last APK given. Some APKs test themselves, but others might test what
      would otherwise be the full app. If you do have multiple APKs, list the
      one which contains the unit test code first, and the code being tested
      second.

      The output of Chrome will be examined for any test related messages, and
      the exit code of the script process will be set according to whether it
      passed or failed.

  driveby [path-to-apk or url-to-apk]
      Start Chrome with an Android APK in drive by mode.

      If no APKs are given, the HelloAndroid.apk is used by default.

  run [path-to-apk]*
      Start Chrome with one or more Android APKs. Only the last one listed has
      its default activity launched.

      If no APKs are given, a sample set is used by default.

  system
      Starts Chrome with ARC system services, but no APK. AdbService is
      enabled so to accept adb commands through the network.

  perftest [path-to-apk]*
      Test that the given APKs can be started and print the time to boot.

      If no APKs are given, a sample set is used by default.

Native Client Debugging

  When debugging NativeClient, you can also increase logging output with
  these environment variables:
    NACL_DEBUG_ENABLE=1
    PPAPI_BROWSER_DEBUG=1
    NACL_PLUGIN_DEBUG=1
    NACL_PPAPI_PROXY_DEBUG=1
    NACL_SRPC_DEBUG=[1-255] (higher is more output)
    NACLVERBOSITY=[1-255] (higher is more output)

""", formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument('mode',
                      choices=('atftest', 'driveby', 'run', 'system',
                               'perftest'),
                      help=argparse.SUPPRESS)

  parser.add_argument('--additional-android-permissions',
                      metavar='<permisions>',
                      help='A comma separated list of additional Android'
                      ' permissions the CRX should declare.',
                      default=None)

  parser.add_argument('--additional-metadata', '-m', default={},
                      type=json.loads,
                      help='Add additional metadata to the crx.')

  parser.add_argument('--arc-strace-output', metavar='<file>',
                      default='out/arc_strace.txt', help='Output file for '
                      '--enable-arc-strace (default: out/arc_strace.txt). '
                      'Use \'stderr\' to send results to stderr.')

  parser.add_argument('--app-template', metavar='<path>', default=None,
                      help='Path to an override app template for apk_to_crx '
                      'packaging.')

  parser.add_argument('--no-cache-warming', action='store_true',
                      help='Works with perftest command only. Not starts the '
                      'plugin page before --iterations start counting.')

  # TODO(crbug.com/313551): Get rid of all duplicated metadata options.
  parser.add_argument('--can-rotate', action='store_true', default=None,
                      help='Indicates that the application can rotate the '
                      'screen, which can affect geometry computations for '
                      'window sizing.')

  parser.add_argument('--chrome-binary', metavar='<path>', default=None,
                      help='The path to the Chrome binary on which ARC '
                      'runs. Note that the directory containing the binary '
                      'needs to contain other data/binaries to run Chrome '
                      '(for example, nacl_helper is needed to be contained). '
                      'Be careful. There can be PPAPI compatibility issues '
                      'when the version of your Chrome binary is very '
                      'different from src/build/DEPS.chrome.')

  parser.add_argument('--chrome-arg', metavar='<arg>', action='append',
                      dest='chrome_args',
                      help='The additional argument for launching the Chrome.')

  parser.add_argument('--crx-name-override', metavar='<path>', default=None,
                      help='The name of the CRX which will be generated '
                      'by this script from an APK. This will be set by '
                      'run_integration_tests to isolate each test. '
                      'The basename of APK will be used if not specified.')

  parser.add_argument('--disable-auto-back-button',
                      action='store_true', default=None,
                      help='Disables automatic enabling/disabling of the '
                      'back button based on the Activity stack.')

  parser.add_argument('--disable-nacl-sandbox', action='store_true',
                      help='Disable NaCl sandbox.')

  parser.add_argument('--display', help='Use given display for Chrome')

  # TODO(crbug.com/313551): Remove this option and make it the default
  # once we remove all individual metadata options and only specify
  # metadata via -m option.
  parser.add_argument('--dogfood-metadata', '-D', action='store_true',
                      help='Use dogfood metadata settings to start this app')

  parser.add_argument('--enable-adb', action='store_true', default=None,
                      help='Enable adb support')

  parser.add_argument('--enable-arc-strace', action='store_true',
                      default=None,
                      help='Enable builtin strace-like tracer of ARC '
                      '(output to --arc-strace-output).')

  parser.add_argument('--enable-compositor', action='store_true',
                      default=None, help='Enable the pepper compositor.')

  parser.add_argument('--enable-fake-video-source', action='store_true',
                      help='Enable a fake video source for testing')

  parser.add_argument('--enable-nacl-list-mappings', action='store_true',
                      help='Enable the nacl_list_mappings call.')

  parser.add_argument('--enable-external-directory', action='store_true',
                      default=None,
                      help='Enable the external directory mounting.')

  parser.add_argument('--enable-osmesa', action='store_true',
                      default=None,
                      help='Enable GL emulation with OSMesa.')

  parser.add_argument('--form-factor', '-f', choices=_ALLOWED_FORMFACTORS,
                      type=_parse_formfactor, default=None,
                      help='Set desired form factor in manifest.')

  parser.add_argument('--gdb', metavar='<targets>', default=[],
                      type=_parse_gdb_targets, help='A comma-seperated list of '
                      'targets to debug. Possible values include: plugin, gpu, '
                      'browser, renderer.')

  parser.add_argument('--gdb-type', choices=('xterm', 'wait', 'screen'),
                      default='xterm', help='Specifies how GDB is launched. '
                      'By default, it is launched under GDB. If you specify '
                      '"wait", the plugin will not run until you attach GDB '
                      'by yourself. Currently "wait" is supported only for '
                      'NaCl plugins.')

  parser.add_argument('--iterations', type=int, metavar='<N>', help='Works '
                      'with perftest command only.  Starts the plugin page <N> '
                      'times and prints average stats.  Starts counting after '
                      'warmup iterations.')

  parser.add_argument('--jdb', dest='jdb_port', action='store_const',
                      default=None, const=8000, help='Wait for a '
                      'JDWP compliant debugger (such as jdb or Eclipse) to '
                      'connect.  Once the user resumes, booting will resume.')

  parser.add_argument('--jdb-port', dest='jdb_port', metavar='<port>',
                      type=int, default=8000, help='Port to use for the JDWP '
                      'debugger. The default is 8000. Implies --jdb')

  parser.add_argument('--logcat', dest='logcat',
                      metavar='[filterspecs]', type=str, nargs='+',
                      default=None, help='Execute adb logcat with given '
                      'filtersepcs.')

  parser.add_argument('--log-load-progress', action='store_true', default=None,
                      help='Log asset and class accesses')

  parser.add_argument('--minimum-lifetime', type=int, default=0,
                      metavar='<T>', help='Works with perftest only. '
                      'Specifies timeout after onResume.')

  parser.add_argument('--minimum-steady', type=int, default=0,
                      metavar='<T>', help='Works with perftest only. '
                      'After onResume, the script waits until either no logs '
                      'are output for the time specified by this flag or '
                      '--timeout seconds have passed after onResume.')

  parser.add_argument('--minimum-launch-delay', type=int, default=None,
                      metavar='<T>', help='Specifies delay in milliseconds for '
                      'launching the app. If set, chrome.app.runtime.onLaunched'
                      ' handler does not create a window for the app until the '
                      'specified time passes.')

  parser.add_argument('--nacl-helper-binary', metavar='<path>',
                      help='The path to nacl_helper binary. This option is '
                      'usable only when both --remote and --gdb=plugin are '
                      'specified. If this is not specified, nacl_helper will '
                      'be copied from the remote host but symbols in '
                      'nacl_helper may not be available.')

  parser.add_argument('--ndk-abi', metavar='<armeabi-v7a/armeabi>',
                      choices=_ALLOWED_NDK_ABIS, help='Set ABI for NDK '
                      'libraries. By default we search for armeabi-v7a library '
                      'and fall back to armeabi.')

  parser.add_argument('--nocrxbuild', dest='build_crx', action='store_false',
                      help='Do not to rebuild the crx - just use what is '
                      'already there.')

  parser.add_argument('--noninja', dest='run_ninja', action='store_false',
                      help='Do not attempt build before running the above '
                      'command.')

  parser.add_argument('--orientation', '-o', choices=_ALLOWED_ORIENTATIONS,
                      type=_parse_orientation,
                      help='Set desired orientation in manifest.')

  parser.add_argument('--output-timeout', type=int, default=None,
                      metavar='<T>', help='Works with atftest, system and '
                      'perftest commands only.  Specifies the timeout in '
                      'seconds for requiring some amount of output from the '
                      'running test. The default is no output timeout.')

  parser.add_argument('--perfstartup', type=int, metavar='<N>', help='Launch '
                      'with perf and collect data for the first <N> seconds. '
                      'Plugin will be killed after this timeout.')

  parser.add_argument('--lang', help='Set language for the Chrome')

  parser.add_argument('--resize', choices=_ALLOWED_RESIZES, default=None,
                      help='Controls the behavior of app/window resizing.')

  # TODO(crbug.com/254164): Get rid of the fake ATF test concept used
  # by NDK tests currently.
  parser.add_argument('--run-test-as-app', action='store_true', help=
                      'Runs a test as an application and not as '
                      'instrumentation.')

  parser.add_argument('--run-test-classes', metavar='<classes>', help=
                      'Used by atftest to specify which test classes to run.')

  parser.add_argument('--run-test-packages', metavar='<packages>', help=
                      'Used by atftest to specify which test packages to run.')

  parser.add_argument('--stderr-log', choices=_ALLOWED_STDERR_LOGS,
                      default=None, help='Minimum console log priority.')

  parser.add_argument('--silent', '-s', action='store_true',
                      help='Sets the default filter spec to silent.')

  parser.add_argument('--start-test-component', metavar='<component>',
                      help='Used by atftest to indicate how to launch the '
                      'tests.')

  parser.add_argument('--timeout', type=int, default=_DEFAULT_TIMEOUT,
                      metavar='<T>', help='Works with atftest, system and '
                      'perftest commands only.  Specifies timeout for running '
                      'test in seconds. Default is ' + str(_DEFAULT_TIMEOUT) +
                      ' sec.')

  parser.add_argument('--disable-sleep-on-blur', action='store_false',
                      default=None, dest='sleep_on_blur',
                      help='Track app window focus and stop updating screen if '
                      'the app is not focused.')

  parser.add_argument('--tracestartup', type=int, metavar='<N>', help='Trace '
                      'from browser startup (the first <N> seconds) to collect '
                      'data for chrome://tracing. Output file is '
                      'chrometrace.log.')

  parser.add_argument('--use-temporary-data-dirs', action='store_true',
                      help='Use a temporary directory as the user data '
                      'directory of Chrome. The launched Chrome has empty '
                      'profile and HTML5 filesystem and they will be '
                      'removed when this script finishes. The ARC data '
                      'directory, which contains the unpacked CRX files, is '
                      'also removed.')

  parser.add_argument('--user-data-dir', metavar='<path>',
                      help='Specify user data dir for Chrome to run')

  parser.add_argument('--verbose', '-v', action='store_true',
                      help='Show verbose logging')

  remote_executor.add_remote_arguments(parser)

  # We do not support '--use-high-dpi=yes/no' here since as of today Chrome's
  # device scale setting is almost always 1.0 at this point except on Pixel
  # where this script is not needed.

  args, opts = parser.parse_known_args(
      launch_chrome_util.remove_leading_launch_chrome_args(argv))

  if not args.dogfood_metadata:
    _set_default_args(args)

  # Inject a few additional attributes to the parsed args that we'll use
  # throughout the rest of this script.
  setattr(args, 'arc_data_dir', None)
  setattr(args, 'apk_path_list', [])
  if not _parse_mode_arguments(opts, args):
    parser.print_help()
    sys.exit(1)

  _validate_mode_settings(parser, args)
  _validate_perftest_settings(parser, args)
  _validate_system_settings(parser, args)
  _validate_debug_modes(parser, args)
  _validate_timeout(parser, args)
  _validate_arc_strace(parser, args)

  _resolve_perf_test_mode(args)
  _setup_filterspec_from_args(args)

  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

  return args
