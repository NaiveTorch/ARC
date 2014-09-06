#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import build_common
import ninja_generator
from build_options import OPTIONS


def _add_compile_flags(ninja):
  if OPTIONS.is_memory_usage_logging():
    ninja.add_defines('MEMORY_USAGE_LOGGING')
  ninja.add_ppapi_compile_flags()  # for mprotect_rwx.cc
  ninja.add_libchromium_base_compile_flags()


def _get_generated_cc_file(ninja, name):
  rule_name = 'gen_%s_cc' % name
  script_name = 'src/common/gen_%s_cc.py' % name
  ninja.rule(rule_name,
             command='%s > $out.tmp && mv $out.tmp $out' % script_name,
             description=rule_name + ' $in')

  gen_dir = os.path.join(build_common.get_build_dir(), 'common_gen_sources')
  cc_filename = os.path.join(gen_dir, '%s.cc' % name)
  implicit = [script_name,
              'src/build/build_options.py',
              'src/build/%s.py' % name]
  ninja.build(cc_filename, rule_name, implicit=implicit)
  return cc_filename


def _get_wrapped_functions_cc(ninja):
  return _get_generated_cc_file(ninja, 'wrapped_functions')


def _get_android_static_libraries_cc(ninja):
  return _get_generated_cc_file(ninja, 'android_static_libraries')


def _generate_libpluginhandle_ninja():
  n = ninja_generator.ArchiveNinjaGenerator('libpluginhandle')
  return n.build_default(['src/common/plugin_handle.cc']).archive()


# Generate libcommon.a, the library that should be linked into everything.
def generate_ninjas():
  n = ninja_generator.ArchiveNinjaGenerator(
      'libcommon_test_main',
      base_path='src/common/tests',
      instances=0)  # Should not be used by production binary.
  sources = n.find_all_sources(include_tests=True)
  n.build_default(sources, base_path=None).archive()

  _generate_libpluginhandle_ninja()

  n = ninja_generator.ArchiveNinjaGenerator('libcommon',
                                            enable_clang=True,
                                            base_path='src/common')
  n.add_compiler_flags('-Werror')
  if build_common.use_ndk_direct_execution():
    n.add_compiler_flags('-DUSE_NDK_DIRECT_EXECUTION')
  # Specify the few include directories needed for building code in
  # common directories.  Common code really should not reach out into
  # external.
  n.add_include_paths('android/system/core/include', 'android_libcommon')
  _add_compile_flags(n)
  sources = n.find_all_sources()
  sources.remove('src/common/plugin_handle.cc')
  sources.append(_get_wrapped_functions_cc(n))
  sources.append(_get_android_static_libraries_cc(n))
  return n.build_default(sources, base_path=None).archive()


def generate_test_ninjas():
  n = ninja_generator.TestNinjaGenerator('libcommon_test',
                                         enable_clang=True,
                                         base_path='src/common')
  n.emit_ld_wrap_flags()
  n.build_default_all_test_sources()
  n.add_compiler_flags('-Werror')
  n.add_library_deps('libgccdemangle.a', 'libwrap_for_test.a')
  _add_compile_flags(n)
  n.run(n.link())
