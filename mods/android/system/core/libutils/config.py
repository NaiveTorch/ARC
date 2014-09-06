# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libutils.so."""

import build_common
import make_to_ninja
import ninja_generator


def _generate_libutils_arc_tests_ninja():
  base_path = 'android/system/core/libutils/arc_tests'
  n = ninja_generator.TestNinjaGenerator(
      'libutils_arc_tests', base_path=base_path)
  n.build_default_all_test_sources()
  n.emit_framework_common_flags()
  n.add_compiler_flags('-Werror')
  n.emit_ld_wrap_flags()
  library_deps = ['libchromium_base.a',  # for libcommon.a etc.
                  'libcommon.a',
                  'libcorkscrew.a',
                  'libcutils.a',
                  'libgccdemangle.a',
                  'libpluginhandle.a',
                  'libutils.so',
                  'libwrap_for_test.a']
  n.add_library_deps(*library_deps)
  n.run(n.link())


def _generate_libutils_ninja():
  def _filter(vars):
    if vars.is_host():
      return False
    # libutils.so is built as a --whole-library shared object of libutils.a.  We
    # do not build both the archive and shared objects for any module because we
    # only use one or the other.
    if vars.get_module_name() == 'libutils' and vars.is_shared():
      return False
    if vars.get_module_name() == 'libutils' and not vars.is_shared():
      make_to_ninja.Filters.convert_to_shared_lib(vars)
    # TODO(crbug.com/364344): Once Renderscript is built from source, this
    # canned install can be removed.
    if not build_common.use_ndk_direct_execution():
      vars.set_canned(True)
    return True
  make_to_ninja.MakefileNinjaTranslator(
      'android/system/core/libutils').generate(_filter)


def generate_ninjas():
  _generate_libutils_ninja()


def generate_test_ninjas():
  _generate_libutils_arc_tests_ninja()
