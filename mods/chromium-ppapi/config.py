# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libchromium_ppapi library."""

import os

import build_common
import build_options
import ninja_generator
import ninja_generator_runner
import staging
import toolchain


# TODO(kmixter): This function is borrowed from the chromium_org libbase
# config.py.  Attempt to eliminate the dependency.
def _add_chromium_base_compiler_flags(n):
  n.add_ppapi_compile_flags()
  n.add_compiler_flags('-Wno-sign-compare', '-Werror')
  # This is needed because the sources related to message loop include jni.h.
  n.add_include_paths('android/libnativehelper/include/nativehelper',
                      'android/system/core/include')


def _generate_chromium_ppapi_c_headers_ninja():
  if not build_common.use_generated_ppapi_c_headers():
    return
  ninja_name = 'libchromium_ppapi_c_headers'
  n = ninja_generator.NinjaGenerator(ninja_name)
  rule_name = 'gen_' + ninja_name
  ppapi_dir = 'chromium-ppapi/ppapi'
  script_path = staging.as_staging(os.path.join(ppapi_dir,
                                                'gen_ppapi_c_headers.py'))

  n.rule(rule_name,
         command=('python %s $in $out' % script_path),
         description=rule_name + ' $out')

  all_generated_headers = []
  out_dir = build_common.get_ppapi_c_headers_dir()
  c_headers_dir = os.path.join(ppapi_dir, 'c')
  for filename in n.find_all_files(c_headers_dir, '.h'):
    out = n.build(os.path.join(out_dir,
                               filename.replace('chromium-ppapi/', '')),
                  rule_name,
                  filename,
                  implicit=[script_path])
    all_generated_headers.extend(out)

  rule_name = 'stamp_' + ninja_name
  n.rule(rule_name, command='touch $out', description=rule_name + ' $out')
  n.build(build_common.get_ppapi_c_headers_stamp(),
          rule_name,
          all_generated_headers)


def _generate_chromium_ppapi_ninja():
  base_path = 'chromium-ppapi/ppapi'
  # TODO(crbug.com/336316): Build libchromium_ppapi as a DSO without -Wl,--wrap.
  # Functions in libchromium_ppapi do not depend on posix_translation/ at all
  # and linking the lowest layer library with --wrap sounds a little bit scary.
  n = ninja_generator.ArchiveNinjaGenerator(
      'libchromium_ppapi', base_path=base_path)
  _add_chromium_base_compiler_flags(n)
  n.add_include_paths('chromium-ppapi/ppapi')
  # native_client/src/include/portability.h expects bits/wordsize.h
  # exists in system header if __native_client__ is defined.
  # This is true for newlib and glibc,
  # but is false for bionic. So, we need an include path to
  # service_runtime's include path which is used in portability.h
  # when __native_client__ is not defined. As this directory has a
  # few more files which are incompatible with bionic, we put this
  # path as the last resort using unusual -idirafter option.
  #
  # TODO(crbug.com/243244): portability.h should check if __BIONIC__
  # is defined (or check __GLIBC__ and _NEWLIB_VERSION before we are
  # public).
  nacl_service_runtime_include_path = staging.as_staging(
      'native_client/src/trusted/service_runtime/include')
  n.add_compiler_flags('-idirafter', nacl_service_runtime_include_path)
  # With this, unistd.h will have environ global variable.
  n.add_defines('_GNU_SOURCE=1')
  if build_options.OPTIONS.is_bare_metal_build():
    # For bare metal build, we get Pepper stubs using NaCl IRT.
    n.add_defines('NACL_LINUX')
    n.add_defines('__native_client__')
    gcc_version = toolchain.get_gcc_version(build_options.OPTIONS.target())
    if build_options.OPTIONS.is_arm() and gcc_version >= [4, 8, 0]:
      # TODO(crbug.com/393385): ARM gcc 4.8 has a bug when doing tail call
      # optimization from softfp to hardfp code. Disable the optimization until
      # the bug is fixed.
      n.add_compiler_flags('-fno-optimize-sibling-calls')

  def relevant(f):
    assert f.startswith(base_path + os.path.sep)
    ppapi_subdir = f.split(os.path.sep)[2]
    if ppapi_subdir in ['c', 'cpp', 'utility']:
      return True
    # This defines the entry point of nexe.
    return 'native_client/src/untrusted/irt_stub' in f

  build_files = filter(relevant, n.find_all_sources())
  n.build_default(build_files, base_path=None,
                  order_only=build_common.get_ppapi_c_headers_stamp())
  n.archive()


def generate_ninjas():
  ninja_generator_runner.request_run_in_parallel(
      _generate_chromium_ppapi_c_headers_ninja,
      _generate_chromium_ppapi_ninja)
