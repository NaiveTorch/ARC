# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# A helper script for programs loaded by the Bare Metal loader.
#

import gdb
import os
import re
import subprocess
import traceback
import time


# The text section in the objdump result looks for something like:
#
# Idx Name         Size      VMA       LMA       File off  Algn
#  8 .text         0006319b  0000bc20  0000bc20  0000bc20  2**4
#                  CONTENTS, ALLOC, LOAD, READONLY, CODE
_TEXT_SECTION_PATTERN = re.compile(r'\.text\s+(?:\w+\s+){3}(\w+)')

# The Bionic loader has a MOD for Bare Metal mode so that it waits GDB
# to attach the process if this file exists. See __linker_init in
# bionic/linker/linker.cpp.
_LOCK_FILE = '/tmp/bare_metal_gdb.lock'


def _get_text_section_file_offset(path):
  """Returns the offset of the text section in the file."""
  objdump_result = subprocess.check_output(['objdump', '-h', path])
  match = _TEXT_SECTION_PATTERN.search(objdump_result.decode())
  if not match:
    return None
  return int(match.group(1), 16)


class LoadHandlerBreakpoint(gdb.Breakpoint):
  def __init__(self, main_binary, library_path, breakpoint_spec,
               name_expr, addr_expr):
    super(LoadHandlerBreakpoint, self).__init__(breakpoint_spec)
    self._main_binary = main_binary
    self._library_path = library_path
    self._name_expr = name_expr
    self._addr_expr = addr_expr

  def _get_binary_path_from_link_map(self):
    # TODO(crbug.com/310118): Use stack address instead of lm->l_name
    # which requires debug info.
    name = gdb.execute('p %s' % self._name_expr, to_string=True)
    # This will be like: $5 = 0x357bc "libc.so"
    matched = re.match(r'.*"(.*)"', name)
    if not matched:
      print('Failed to retrieve the name of the shared object: %s' % name)
      return None

    path = matched.group(1)
    # Check if this is the main binary before the check for
    # "lib" to handle tests which start from lib such as libndk_test
    # properly.
    if path == os.path.basename(self._main_binary) or path == 'main.nexe':
      path = self._main_binary
    else:
      # Some files are in a subdirectory. So search files in the _library_path.
      for dirpath, _, filenames in os.walk(self._library_path):
        if path in filenames:
          path = os.path.join(dirpath, path)
          break

    if not os.path.exists(path):
      # TODO(crbug.com/354290): In theory, we should be able to
      # extract the APK and tell GDB the path to the NDK shared
      # object.
      print('%s does not exist! Maybe NDK in APK?' % path)
      return None

    return path

  def _get_text_section_address_from_link_map(self, path):
    base_addr_line = gdb.execute('p %s' % self._addr_expr, to_string=True)
    # This will be like: $3 = 4148191232
    matched = re.match(r'.* = (\d+)', base_addr_line)
    if not matched:
      print('Failed to retrieve the address of the shared object: %s' %
            base_addr_line)
      return None
    base_addr = int(matched.group(1))

    file_off = _get_text_section_file_offset(path)
    if file_off is None:
      print('Unexpected objdump output for %s' % path)
      return None
    return file_off + base_addr

  def stop(self):
    """Called when _NOTIFY_GDB_OF_LOAD_FUNC_NAME function is executed."""
    try:
      path = self._get_binary_path_from_link_map()
      if not path:
        return False

      text_addr = self._get_text_section_address_from_link_map(path)
      if text_addr is None:
        print('Type \'c\' or \'continue\' to keep debugging')
        # Return True to stop the execution.
        return True

      gdb.execute('add-symbol-file %s 0x%x' % (path, text_addr))
      return False
    except:
      print(traceback.format_exc())
      return True


def _get_program_loaded_address(path):
  path_suffix = '/' + os.path.basename(path)
  while True:
    mapping = gdb.execute('info proc mapping', to_string=True)
    for line in mapping.splitlines():
      # Here is the list of columns:
      # 1) Start address.
      # 2) End address.
      # 3) Size.
      # 4) Offset.
      # 5) Pathname.
      # For example:
      # 0xf5627000 0xf5650000 0x29000 0x0 /ssd/arc/out/.../runnable-ld.so
      column_list = line.split()
      if len(column_list) == 5 and column_list[4].endswith(path_suffix):
        return int(column_list[0], 16)
    print('Failed to find the loaded address of ' + path +
          ', retrying...')
    time.sleep(0.1)


def init(arc_nexe, library_path, runnable_ld_path, remote_address=None,
         ssh_options=None):
  """Initializes GDB plugin for nacl_helper in Bare Metal mode.

  If remote_address is specified, we control the _LOCK_FILE using this
  address. This should be specified only for Chrome OS.
  """
  program_address = (_get_program_loaded_address(runnable_ld_path) +
                     _get_text_section_file_offset(runnable_ld_path))
  gdb.execute('add-symbol-file %s 0x%x' % (runnable_ld_path, program_address))
  LoadHandlerBreakpoint(arc_nexe, library_path,
                        'notify_gdb_of_load', 'info->name', 'info->base')
  # Everything gets ready, so unlock the program.
  if remote_address:
    command = ['ssh', 'root@%s' % remote_address]
    if ssh_options:
      command.extend(ssh_options)
    command.extend(['rm', _LOCK_FILE])
    subprocess.check_call(command)
  else:
    os.unlink(_LOCK_FILE)


def init_for_unittest(bare_metal_loader, test_binary, library_path):
  LoadHandlerBreakpoint(
      test_binary, library_path,
      'bare_metal::bare_metal_irt_notify_gdb_of_load',
      'lm->l_name', 'lm->l_addr')
  # TODO(crbug.com/310118): It seems only very recent GDB has
  # remove-symbol-file. Create a hook for unload events once we switch
  # to recent GDB.
