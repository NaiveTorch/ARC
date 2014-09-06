#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Runs unittests for NaCl or Bare Metal under GDB.
#

import os
import signal
import subprocess
import sys

import build_common
import toolchain
from build_options import OPTIONS
from util import gdb_util


def _run_gdb_for_nacl(args, test_args):
  runnable_ld = args[-1]
  assert 'runnable-ld.so' in runnable_ld
  # Insert -g flag before -a to let sel_ldr wait for GDB.
  a_index = args.index('-a')
  assert 'sel_ldr' in args[a_index - 1]
  args.insert(a_index, '-g')
  args.extend(test_args)
  # The child process call setsid(2) to create a new session so that
  # sel_ldr will not die by Ctrl-C either. Note that ignoring SIGINT
  # does not work for sel_ldr, because sel_ldr will override the
  # setting.
  sel_ldr_proc = subprocess.Popen(args, stderr=subprocess.STDOUT,
                                  preexec_fn=os.setsid)

  gdb = toolchain.get_tool(OPTIONS.target(), 'gdb')
  irt = toolchain.get_tool(OPTIONS.target(), 'irt')
  subprocess.call([
      gdb,
      '-ex', 'target remote :4014',
      '-ex', 'nacl-irt %s' % irt,
      # The Bionic does not pass a fullpath of a shared object to the
      # debugger. Fixing this issue by modifying the Bionic loader
      # will need a bunch of ARC MOD. We work-around the issue by
      # passing the path of shared objects here.
      #
      # GDB uses NaCl Manifest file for arc.nexe so we do not need
      # this for launch_chrome.
      '-ex', 'set solib-search-path %s' %
      build_common.get_load_library_path(),
      '-ex',
      'echo \n*** Type \'continue\' or \'c\' to start debugging ***\n\n',
      runnable_ld])
  sel_ldr_proc.kill()


def _get_gdb_command_to_inject_bare_metal_gdb_py(main_binary):
  bare_metal_gdb_init_args = map(gdb_util.to_python_string_literal, [
      build_common.get_bare_metal_loader(),
      main_binary,
      build_common.get_load_library_path(),
  ])

  # This GDB command sequence initializes the Python script for GDB to
  # load shared objects in Bare Metal mode properly.
  return ['-ex', 'python sys.path.insert(0, "src/build")',
          '-ex', 'python from util import bare_metal_gdb',
          '-ex', 'python bare_metal_gdb.init_for_unittest(%s)' % (
              ', '.join(bare_metal_gdb_init_args))]


def _run_gdb_for_bare_metal_arm(runner_args, test_args):
  gdb = toolchain.get_tool(OPTIONS.target(), 'gdb')
  bare_metal_loader_index = runner_args.index(
      build_common.get_bare_metal_loader())

  # For Bare Metal ARM, we use qemu's remote debugging interface.
  args = (runner_args[:bare_metal_loader_index] +
          ['-g', '4014'] +
          runner_args[bare_metal_loader_index:] + test_args)
  # Create a new session using setsid. See the comment in
  # _run_gdb_for_nacl for detail.
  qemu_arm_proc = subprocess.Popen(args, stderr=subprocess.STDOUT,
                                   preexec_fn=os.setsid)

  gdb_command = _get_gdb_command_to_inject_bare_metal_gdb_py(test_args[0])

  args = ([gdb, '-ex', 'target remote :4014'] +
          gdb_command +
          gdb_util.get_args_for_stlport_pretty_printers() +
          ['-ex',
           'echo \n*** Type \'continue\' or \'c\' to start debugging ***\n\n',
           build_common.get_bare_metal_loader()])
  subprocess.call(args)

  qemu_arm_proc.kill()


def _run_gdb_for_bare_metal(runner_args, test_args):
  gdb = toolchain.get_tool(OPTIONS.target(), 'gdb')
  bare_metal_loader_index = runner_args.index(
      build_common.get_bare_metal_loader())

  gdb_command = _get_gdb_command_to_inject_bare_metal_gdb_py(test_args[0])

  args = (runner_args[:bare_metal_loader_index] +
          [gdb] +
          gdb_command +
          gdb_util.get_args_for_stlport_pretty_printers() +
          ['-ex',
           'echo \n*** Type \'run\' or \'r\' to start debugging ***\n\n',
           '--args'] +
          runner_args[bare_metal_loader_index:] +
          test_args)
  subprocess.call(args)


def main():
  OPTIONS.parse_configure_file()
  test_args = sys.argv[1:]
  if not test_args:
    print 'Usage: %s test_binary [test_args...]' % sys.argv[0]
    sys.exit(1)

  # This script must not die by Ctrl-C while GDB is running. We simply
  # ignore SIGINT. Note that GDB will still handle Ctrl-C properly
  # because GDB sets its signal handler by itself.
  signal.signal(signal.SIGINT, signal.SIG_IGN)

  runner_args = toolchain.get_tool(OPTIONS.target(), 'runner').split()
  if OPTIONS.is_nacl_build():
    _run_gdb_for_nacl(runner_args, test_args)
  elif OPTIONS.is_bare_metal_build():
    if OPTIONS.is_arm():
      _run_gdb_for_bare_metal_arm(runner_args, test_args)
    else:
      _run_gdb_for_bare_metal(runner_args, test_args)


if __name__ == '__main__':
  sys.exit(main())
