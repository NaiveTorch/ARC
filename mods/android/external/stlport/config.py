#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import build_common
import ninja_generator
from build_options import OPTIONS
from make_to_ninja import MakefileNinjaTranslator

_STLPORT_ROOT = 'android/external/stlport'

_EXCLUDE_FILES = [
    # Target duplication. There is string_header_test.cpp.
    'string_header_test.c',

    # Link fails on NaCl i686 and NaCl x86-64.
    # Need to add "-fexceptions" for cxx flag for compile.
    'exception_test.cpp',

    # Compile fails on GCC >= 4.7 due to extra unqualified
    # lookups. (http://gcc.gnu.org/gcc-4.7/porting_to.html)
    'rope_test.cpp',

    # Link fails on NaCl x86-64.
    'cmath_test.cpp',
    'codecvt_test.cpp',
]

_EXCLUDE_TESTS = [
    # Float precision error due to sprinf for formatting.
    'NumPutGetTest::num_put_float',
    'NumPutGetTest::num_get_float',
    'NumPutGetTest::custom_numpunct',

    # /dev/null is not allowd on NaCl host.
    'FstreamTest::null_stream',

    # wchar_t is not available on bionic.
    'IOStreamTest::in_avail',
    'LimitTest::test',

    # Opening directory with open(2) on NaCl fails.
    # This should not be a problem on production ARC because
    # file opening is managed with posix_translation.
    'FstreamTest::input',

    # istr.imbue hang up. Seems locale is not suppoteded.
    'CodecvtTest::variable_encoding',

    # Tests are failed on qemu but not on real devices.
    'StringTest::mt',
    'HashTest::hmmap2'
]


def get_libstlport_static_defines():
  # Add -D_STLP_USE_STATIC_LIB so that STLPort is compiled without any
  # __attribute__((visibility("default"))) attributes. This should
  # actually be done in Android.mk, but Android folks seems to have
  # forgotten to use it.
  # TODO(crbug.com/417327): Fix the upstream Android.mk file.
  return ['-D_STLP_USE_STATIC_LIB']


def generate_ninjas():
  def _filter(vars):
    # STLport does not have compiler dependent functions (functions which are
    # called from code generated by compiler). Android uses libstdc++ in bionic
    # instead of GCC's libstdc++. We also use bionic's and link it into
    # libstlport.so for simplicity.
    vars.get_sources().extend([
        'android/bionic/libstdc++/src/new.cpp',
        'android/bionic/libstdc++/src/one_time_construction.cpp',
        'android/bionic/libstdc++/src/pure_virtual.cpp',
        'android/bionic/libstdc++/src/typeinfo.cpp'])
    vars.get_includes().append('android/bionic/libc')
    vars.get_includes().remove('android/bionic/libstdc++/include')
    # This is necessary to use atomic operations in bionic. 1 indicates
    # compilation for symmetric multi-processor (0 for uniprocessor).
    vars.get_cflags().append('-DANDROID_SMP=1')
    # This is for not emitting syscall wrappers.
    if not vars.is_static():
      vars.get_shared_deps().extend(['libc', 'libm'])
      vars.get_generator_args()['is_system_library'] = True
      # TODO(crbug.com/364344): Once Renderscript is built from source, this
      # canned install can be removed.
      if not build_common.use_ndk_direct_execution():
        vars.set_canned(True)
    else:
      vars.get_cflags().extend(get_libstlport_static_defines() + [
          '-fvisibility=hidden', '-fvisibility-inlines-hidden'])
    return True
  MakefileNinjaTranslator(_STLPORT_ROOT).generate(_filter)


def generate_test_ninjas():
  n = ninja_generator.TestNinjaGenerator(
      'stlport_unittest',
      base_path=_STLPORT_ROOT + '/test/unit')

  n.add_c_flags('-Werror')
  n.add_cxx_flags('-Werror')

  # For avoiding compile failure on min_test.cpp.
  n.add_cxx_flags('-Wno-sequence-point')

  # For avoiding compile failure on sstream_test.cpp and time_facets_test.cpp.
  n.add_cxx_flags('-Wno-uninitialized')

  # For avoiding compile failure on --disable-debug-code.
  n.add_cxx_flags('-Wno-maybe-uninitialized')

  n.build_default(
      n.find_all_files(_STLPORT_ROOT + '/test/unit',
                       ['.cpp', '.c'],
                       include_tests=True,
                       exclude=_EXCLUDE_FILES),
      base_path=None)

  argv = '-x=%s' % ','.join(_EXCLUDE_TESTS)
  n.run(n.link(), argv=argv, enable_valgrind=OPTIONS.enable_valgrind(),
        rule='run_test')
