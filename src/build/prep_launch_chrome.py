#!/usr/bin/python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This module provides a function to prepare unpacked CRXs that are necessary
# to run Chrome with ARC.
# When this script is invoked, it accepts the same options as those of
# launch_chrome.py and prepares the files that would be needed to invoke
# launch_chrome.py with the same options. This usage is intended mainly for
# generating files which are needed to run Chrome remotely on a Chrome OS
# device.

import atexit
import json
import os
import shutil
import sys

import build_common
import launch_chrome_options

from build_options import OPTIONS

_DOGFOOD_METADATA_PATH = 'third_party/examples/opaque/dogfood.meta'
_ROOT_DIR = build_common.get_arc_root()
sys.path.append(os.path.join(_ROOT_DIR, 'src', 'packaging'))
import apk_to_crx


def _remove_ndk_libraries(apk_path):
  """Remove ndk libraries installed by previous launches.

  Package Manager installs shared libraries that match ABI but it doesn't
  remove them from previous installation.  If apk does not contain the library
  for current ABI, installer does not produce an error.  In this case
  application may launch successfully using previously installed library.  We
  want to see an error instead.
  """
  apk_name = os.path.splitext(os.path.basename(apk_path))[0]
  if apk_name:
    native_library_directory = os.path.join(_ROOT_DIR,
                                            build_common.get_android_root(),
                                            'data', 'app-lib',
                                            apk_name)
    shutil.rmtree(native_library_directory, ignore_errors=True)


def _generate_shell_command(parsed_args):
  shell_cmd = []
  if parsed_args.mode == 'atftest' and not parsed_args.run_test_as_app:
    target = '$instrument'
    if parsed_args.start_test_component:
      target = parsed_args.start_test_component
    shell_cmd.extend(['am', 'instrument'])
    if parsed_args.run_test_classes:
      shell_cmd.extend(['-e', 'class', parsed_args.run_test_classes])
    if parsed_args.run_test_packages:
      shell_cmd.extend(['-e', 'package', parsed_args.run_test_packages])
    shell_cmd.extend(['-r', '-w', target, ';'])
    shell_cmd.extend(['stop', ';'])
  return shell_cmd


def _convert_launch_chrome_options_to_external_metadata(parsed_args):
  metadata = parsed_args.additional_metadata

  arg_to_metadata = (('can_rotate', 'canRotate'),
                     ('disable_auto_back_button', 'disableAutoBackButton'),
                     ('enable_adb', 'enableAdb'),
                     ('enable_arc_strace', 'enableArcStrace'),
                     ('enable_compositor', 'enableCompositor'),
                     ('enable_external_directory', 'enableExternalDirectory'),
                     ('form_factor', 'formFactor'),
                     ('jdb_port', 'jdbPort'),
                     ('log_load_progress', 'logLoadProgress'),
                     ('minimum_launch_delay', 'minimumLaunchDelay'),
                     ('ndk_abi', 'ndkAbi'),
                     ('orientation', 'orientation'),
                     ('resize', 'resize'),
                     ('stderr_log', 'stderrLog'),
                     ('sleep_on_blur', 'sleepOnBlur'))

  for arg_name, metadata_name in arg_to_metadata:
    value = getattr(parsed_args, arg_name, None)
    if value is not None:
      metadata[metadata_name] = value

  is_slow_debug_run = bool(parsed_args.jdb_port or parsed_args.gdb)
  if is_slow_debug_run:
    metadata['isSlowDebugRun'] = is_slow_debug_run
    metadata['sleepOnBlur'] = False

  if (parsed_args.mode == 'atftest' or parsed_args.mode == 'system' or
      OPTIONS.get_system_packages()):
    # An app may briefly go through empty stack while running
    # addAccounts() in account manager service.
    # TODO(igorc): Find a more precise detection mechanism to support GSF,
    # implement empty stack timeout, or add a flag if this case is more common.
    metadata['allowEmptyActivityStack'] = True

  command = _generate_shell_command(parsed_args)
  if command:
    metadata['shell'] = command

  return metadata


def _generate_apk_to_crx_args(parsed_args, metadata=None,
                              combined_metadata_file=None):
  crx_args = []
  crx_args.extend(parsed_args.apk_path_list)
  if parsed_args.verbose:
    crx_args.extend(['--verbose'])
  if parsed_args.mode == 'system':
    crx_args.extend(['--system'])
  crx_args.extend(['--badging-check', 'suppress'])
  crx_args.extend(['--destructive'])
  if parsed_args.app_template:
    crx_args.extend(['--template', parsed_args.app_template])
  if metadata:
    with build_common.create_tempfile_deleted_at_exit() as metadata_file:
      json.dump(metadata, metadata_file)
    crx_args.extend(['--metadata', metadata_file.name])
  if combined_metadata_file:
    crx_args.extend(['--combined-metadata', combined_metadata_file])
  crx_args.extend(['-o', parsed_args.arc_data_dir])
  additional_permissions = []
  if parsed_args.additional_android_permissions:
    additional_permissions.extend(
        parsed_args.additional_android_permissions.split(','))
  if parsed_args.jdb_port or parsed_args.enable_adb:
    additional_permissions.append('INTERNET')
  if additional_permissions:
    crx_args.extend(['--additional-android-permissions',
                     ','.join(additional_permissions)])
  return crx_args


def _build_crx(parsed_args):
  external_metadata = _convert_launch_chrome_options_to_external_metadata(
      parsed_args)
  if not parsed_args.dogfood_metadata:
    apk_to_crx_args = _generate_apk_to_crx_args(
        parsed_args,
        metadata=external_metadata)
  else:
    apk_to_crx_args = _generate_apk_to_crx_args(
        parsed_args,
        metadata=external_metadata,
        combined_metadata_file=_DOGFOOD_METADATA_PATH)
  if not apk_to_crx.build_crx(apk_to_crx_args):
    return False
  return True


def prepare_crx(parsed_args):
  for apk_path in parsed_args.apk_path_list:
    _remove_ndk_libraries(apk_path)
  if parsed_args.build_crx:
    if not _build_crx(parsed_args):
      return -1
  return 0


def prepare_crx_with_raw_args(args):
  parsed_args = launch_chrome_options.parse_args(args)
  return prepare_crx(parsed_args)


def update_shell_command(args):
  """Update the shell command of arc_metadata in the CRX manifest."""
  parsed_args = launch_chrome_options.parse_args(args)
  manifest_path = os.path.join(parsed_args.arc_data_dir, 'manifest.json')
  with open(manifest_path) as f:
    manifest = json.load(f)
  arc_metadata = manifest['arc_metadata']
  shell_command = _generate_shell_command(parsed_args)
  if not shell_command:
    return
  arc_metadata['shell'] = shell_command
  with open(manifest_path, 'w') as f:
    f.write(apk_to_crx.get_metadata_as_json(manifest))


def remove_crx_at_exit_if_needed(parsed_args):
  """Remove the unpacked CRX directory at exit if needed.

  Here are major scenarios where this function is used and the CRX directory is
  removed at the end of the script.
  * When launch_chrome is invoked with --use-temporary-data-dirs, the CRX
    directory is removed.
  * run_integration_tests removes the CRX directory used for the tests by using
    this function at the finalize step.

  NOTE: When --nocrxbuild is specified for launch_chrome.py
  (i.e. parsed_args.build_crx == False), this means the CRX is not created on
  the fly at the beginning of launch_chrome.py but created in a different way
  (e.g created in the previous run, copied from a remote machine, and packaged
  manually by running apk_to_crx.py). In such cases, the CRX is considered as
  special one and preserved even if --use-temporary-data-dirs is specified.
  """
  def remove_arc_data_dir():
    if os.path.exists(parsed_args.arc_data_dir):
      build_common.rmtree_with_retries(parsed_args.arc_data_dir)
  if parsed_args.use_temporary_data_dirs and parsed_args.build_crx:
    atexit.register(remove_arc_data_dir)
