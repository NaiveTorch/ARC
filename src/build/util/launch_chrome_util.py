#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re


_LAUNCH_CHROME_COMMAND_REG = re.compile(r'launch_chrome(\.py)?')

# These arguments to launch_chrome are only meant to be used by the integration
# test infrastructure, and might lead to confusing results if someone copies and
# pastes the command line we issue.
_LAUNCH_CHROME_ARGS_TO_FILTER = (
    # This option is added to isolate the execution of multiple tests and to
    # enable them to run in parallel. This is unnecessary when running a
    # single test manually.
    '--use-temporary-data-dirs',
    # This is added to avoid rebuilding the CRX for the test, which is
    # built in the prepare step of the integration tests. This needs to be
    # omitted when running a test manually with launch_chrome command.
    '--nocrxbuild')


def get_launch_chrome_command(options=None):
  if options is None:
    options = []
  # Run launch_chrome script using /bin/sh so that the script can be executed
  # even if it is on the filesystem with noexec option (e.g. Chrome OS)
  return ['/bin/sh', 'launch_chrome'] + options


def _parse_launch_chrome_command(args):
  if args[0] == 'xvfb-run':
    if '/bin/sh' in args:
      args = args[args.index('/bin/sh'):]
  if args[0] == '/bin/sh':
    args = args[1:]
  return args


def is_launch_chrome_command(argv):
  args = _parse_launch_chrome_command(argv)
  return bool(_LAUNCH_CHROME_COMMAND_REG.match(
      os.path.basename(os.path.realpath(args[0]))))


def remove_leading_launch_chrome_args(argv):
  """Removes the leading args of launch chrome command except option args.

  Examples:
    ['/bin/sh', './launch_chrome', 'run', '-v'] => ['run', '-v']
    ['./launch_chrome', 'run', '--noninja'] => ['run', '--noninja']
  """
  assert(is_launch_chrome_command(argv))
  args = _parse_launch_chrome_command(argv)
  return args[1:]


def split_launch_chrome_args(args):
  """Split the arguments for launching chrome into (safe_args, unsafe_args).

  safe_args is the arguments that are suitable for debugging use by
  copy-and-paste. unsafe_args is the arguments that are intended for the use in
  the integration test framework and unsuitable for debugging use.
  """
  safe_args = filter(lambda x: x not in _LAUNCH_CHROME_ARGS_TO_FILTER, args)
  unsafe_args = filter(lambda x: x in _LAUNCH_CHROME_ARGS_TO_FILTER, args)
  return (safe_args, unsafe_args)
