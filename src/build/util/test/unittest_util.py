#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import build_common
import build_options
import toolchain


def get_nacl_tools():
  """Returns a list of the NaCl tools that are needed to run unit tests."""
  if build_options.OPTIONS.is_bare_metal_build():
    return [build_common.get_bare_metal_loader()]

  bitsize = build_options.OPTIONS.get_target_bitsize()
  arch = 'x86_%d' % bitsize
  nacl_tools = [toolchain.get_nacl_tool('sel_ldr_%s' % arch),
                toolchain.get_nacl_tool('irt_core_%s.nexe' % arch),
                os.path.join(toolchain.get_nacl_toolchain_libs_path(bitsize),
                             'runnable-ld.so')]
  return [os.path.relpath(nacl_tool, build_common.get_arc_root())
          for nacl_tool in nacl_tools]


def get_test_executables(tests):
  """Returns a list of the unit test executables."""
  return [build_common.get_build_path_for_executable(test) for test in tests]


def get_all_tests():
  """Returns the list of all unittest names."""
  test_info_dir = build_common.get_remote_unittest_info_path()
  test_info_files = os.listdir(test_info_dir)
  tests = set()
  for test_info_file in test_info_files:
    # test info file name is something like bionic_test.1.json.
    m = re.match(r'(.+)\.[0-9]+\.json', test_info_file)
    if not m:
      continue
    tests.add(m.group(1))
  return sorted(tests)
