#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ninja_generator
from build_options import OPTIONS

_ARC_WRAP_SOURCES = ['android/bionic/libc/bionic/arc_dir_wrap.cpp',
                     'android/bionic/libc/bionic/arc_scandir_wrap.cpp']


def _add_defines(ninja):
  ninja.add_libchromium_base_compile_flags()
  if OPTIONS.use_verbose_memory_viewer():
    ninja.add_defines('USE_VERBOSE_MEMORY_VIEWER')


def _generate_libwrap_ninja():
  ninja = ninja_generator.ArchiveNinjaGenerator('libwrap',
                                                base_path='src/wrap',
                                                enable_clang=True)
  sources = ninja.find_all_sources()
  sources.extend(_ARC_WRAP_SOURCES)
  ninja.add_compiler_flags('-Werror')
  _add_defines(ninja)
  return ninja.build_default(sources, base_path=None).archive()


def _generate_libwrap_for_test_ninja():
  ninja = ninja_generator.ArchiveNinjaGenerator('libwrap_for_test',
                                                base_path='src/wrap',
                                                instances=0,
                                                enable_clang=True)
  sources = ninja.find_all_sources()
  sources.extend(_ARC_WRAP_SOURCES)
  ninja.add_compiler_flags('-Werror')
  _add_defines(ninja)
  ninja.add_defines('LIBWRAP_FOR_TEST')
  return ninja.build_default(sources, base_path=None).archive()


def generate_ninjas():
  _generate_libwrap_ninja()
  _generate_libwrap_for_test_ninja()
