#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# TODO(nativeclient:3734): Remove this directory once we have upstreamed
# everything in this directory to NaCl. NaCl side bug:
# https://code.google.com/p/nativeclient/issues/detail?id=3734
#

import re
import subprocess

import ninja_generator
import ninja_generator_runner
from build_options import OPTIONS
from ninja_generator import ArchiveNinjaGenerator
from ninja_generator import ExecNinjaGenerator
from ninja_generator import TestNinjaGenerator
from ninja_generator import CNinjaGenerator


def _run_pkg_config(args):
  return subprocess.check_output(['pkg-config'] + args).strip()


def _remove_isystem(flags):
  return re.sub(r' -isystem \S+', '', flags)


def _set_bare_metal_flags(n):
  asmflags = _remove_isystem(CNinjaGenerator.get_asmflags())
  # We do not use Bionic for Bare Metal loader. So, we remove all
  # adjustments for include flags.
  asmflags = asmflags.replace(' -nostdinc', '')
  asmflags = asmflags.replace(' -D__ANDROID__', '')
  n.variable('asmflags', asmflags)
  use_64bit_offsets = ' -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64'
  # We always use "hard" ABI on ARM for the helper process.
  if OPTIONS.is_arm():
    use_hard_abi = ' -mfloat-abi=hard'
  else:
    use_hard_abi = ''
  cflags = _remove_isystem(CNinjaGenerator.get_cflags())
  cflags += use_64bit_offsets
  cflags += use_hard_abi
  cflags += ' -Werror'
  n.variable('cflags', cflags)
  cxxflags = _remove_isystem(CNinjaGenerator.get_cxxflags())
  cxxflags = cxxflags.replace(' -nostdinc++', '')
  cxxflags += use_64bit_offsets
  cxxflags += use_hard_abi
  cxxflags += ' -Werror'
  n.variable('cxxflags', cxxflags)
  ninja_generator.CNinjaGenerator.emit_optimization_flags(n)
  n.add_ppapi_compile_flags()
  n.add_libchromium_base_compile_flags()
  n.add_defines('_GNU_SOURCE')


def _link_for_bare_metal(n):
  ldflags = n.get_ldflags()
  # We use glibc in host, so need to drop -nostdlib.
  ldflags = ldflags.replace(' -nostdlib', '')
  if OPTIONS.is_arm():
    # Expand $commonflags and remove -mfloat-abi=softfp, because passing both
    # -mfloat-abi=softfp and hard can confuse the linker.
    ldflags = ldflags.replace('$commonflags', CNinjaGenerator.get_commonflags())
    ldflags = ldflags.replace(' -mfloat-abi=softfp', '')
    # We always use "hard" ABI for the helper process.
    ldflags += ' -mfloat-abi=hard'
  return n.link(variables={'ldflags': ldflags, 'ldadd': '-lrt'})


def _generate_test_framework_for_bare_metal_ninjas():
  n = ArchiveNinjaGenerator('libgtest_glibc', base_path='googletest/src',
                            instances=0)  # Not used by shared objects
  _set_bare_metal_flags(n)
  n.add_include_paths('third_party/googletest')
  n.build_default(['gtest_main.cc', 'gtest-all.cc']).archive()

  n = ArchiveNinjaGenerator('libgmock_glibc', base_path='testing/gmock/src',
                            instances=0)  # Not used by shared objects
  _set_bare_metal_flags(n)
  n.add_include_paths('testing/gmock', 'third_party/testing/gmock/include')
  n.build_default(['gmock-all.cc']).archive()


def _generate_bare_metal_ninjas():
  n = ArchiveNinjaGenerator('libbare_metal',
                            base_path='src/bare_metal/common')
  _set_bare_metal_flags(n)
  # For linker_phdr.c, grabbed from the Bionic loader.
  n.add_c_flags('-std=c99')
  n.add_defines('FOR_BARE_METAL_LOADER')

  sources = n.find_all_sources()
  # We reuse conversion functions for timespec and timeval, which we
  # implemented for Bionic.
  sources.extend(['android/bionic/libc/arch-nacl/syscalls/nacl_timespec.c',
                  'android/bionic/libc/arch-nacl/syscalls/nacl_timeval.c',
                  'android/bionic/linker/linker_phdr.cpp'])
  n.build_default(sources, base_path=None)
  n.archive()

  # Though the bare_metal_loader is not a library, we specify
  # is_system_library=True to prevent CNinjaGenerator from linking
  # this binary against Bionic libc. Note that we cannot use host=True
  # for Bare Metal ARM.
  n = ExecNinjaGenerator('bare_metal_loader',
                         base_path='src/bare_metal/loader',
                         install_path='/bin',
                         is_system_library=True)
  _set_bare_metal_flags(n)
  n.add_whole_archive_deps('libbare_metal.a')
  n.build_default_all_sources()
  _link_for_bare_metal(n)


def generate_ninjas():
  if not OPTIONS.is_bare_metal_build():
    return
  ninja_generator_runner.request_run_in_parallel(
      _generate_bare_metal_ninjas)


def _generate_bare_metal_test_ninjas():
  # Though the libbare_metal_test is not a library, we specify
  # is_system_library=True to prevent CNinjaGenerator from linking
  # this binary against Bionic libc.
  n = TestNinjaGenerator('libbare_metal_test',
                         base_path='src/bare_metal/common',
                         is_system_library=True)
  _set_bare_metal_flags(n)
  n.add_whole_archive_deps('libbare_metal.a')
  n.build_default_all_test_sources()
  build_out = _link_for_bare_metal(n)
  # As src/bare_metal is an ephemeral implementation, we do not run
  # the test under valgrind not to complicate toolchain.py.
  if not OPTIONS.enable_valgrind():
    n.run(build_out)


def generate_test_ninjas():
  if not OPTIONS.is_bare_metal_build():
    return
  ninja_generator_runner.request_run_in_parallel(
      _generate_bare_metal_test_ninjas,
      _generate_test_framework_for_bare_metal_ninjas)
