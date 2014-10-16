# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build miscellaneous open sourced components.

All rules in this file must be appropriate for open sourcing.  Please avoid
adding rules to this file unless they are rules for the overall project
or for third party directories that can be open sourced.
"""

import os

import analyze_diffs
import build_common
import lint_source
import ninja_generator
import ninja_generator_runner
import open_source
import staging

from build_options import OPTIONS
from ninja_generator import ArchiveNinjaGenerator
from ninja_generator import NinjaGenerator


_ANDROID_SYSTEM_IMAGE_DIR = 'ndk/platforms/android-19'


def _generate_test_framework_ninjas():
  n = ArchiveNinjaGenerator('libgtest', base_path='googletest/src',
                            instances=0)  # Not used by shared objects
  n.add_include_paths('third_party/googletest')
  n.build_default(['gtest_main.cc', 'gtest-all.cc']).archive()

  n = ArchiveNinjaGenerator('libgmock', base_path='testing/gmock/src',
                            instances=0)  # Not used by shared objects
  n.add_include_paths('testing/gmock', 'third_party/testing/gmock/include')
  n.build_default(['gmock-all.cc']).archive()


def _generate_breakpad_ninja():
  allowed_dirs = ['common', 'linux', 'dwarf']
  n = ArchiveNinjaGenerator(
      'libbreakpad_common',
      base_path='breakpad/src/common',
      host=True)
  n.add_include_paths('breakpad/src')
  # 19 files in breakpad includes "third_party/lss/linux_syscall_support.h".
  # We use -idirafter instead of the normal -I. third_party/.. is the top
  # directory of ARC and developers may put some files whose name
  # conflicts with standard headers. For example, if one puts "new" at the
  # top of ARC source tree, ARC will not build if we use -I here.
  n.add_compiler_flags('-idirafter', 'third_party/..')
  n.add_cxx_flags('-frtti')  # Breakpad uses RTTI.
  n.add_defines('HAVE_A_OUT_H')
  all_sources = n.find_all_sources()
  all_sources = [s for s in all_sources if not s.endswith('test.cc')]
  all_sources = [
      s for s in all_sources
      if not os.path.basename(os.path.dirname(s)) not in allowed_dirs]
  n.build_default(all_sources, base_path=None).archive()

  for tool, directory_name, cc in [
      ['symupload', 'symupload', 'sym_upload.cc'],
      ['dump_syms', 'dump_syms', 'dump_syms.cc'],
      ['minidump-2-core-x86-64', 'md2core', 'minidump-2-core.cc']]:
    n = ninja_generator.ExecNinjaGenerator(
        tool, host=True,
        base_path='breakpad/src/tools/linux/' + directory_name)
    n.add_include_paths('third_party/breakpad/src')
    # Workaround for third_party/lss/linux_syscall_support.h
    n.add_compiler_flags('-idirafter', 'third_party/..')
    n.add_library_deps('libbreakpad_common.a')
    n.build_default([cc]).link()


def _generate_lint_test_ninjas():
  n = NinjaGenerator('analyze_diffs_test')
  script = 'src/build/analyze_diffs.py'
  n.rule('analyze_diffs_test_fail',
         command=('if %s --under_test $in > $output_path 2>&1; then '
                  '  echo "Expected failure, but there was none"; exit 1; '
                  'else '
                  '  if ! diff $output_path $in.fail > $out; then '
                  '    echo "Differences from expected errors:"; '
                  '    cat $out; '
                  '    rm -f $out; '
                  '    echo "To update: cp $output_path $in.fail"; '
                  '    exit 1; '
                  '  fi; '
                  'fi' % script),
         description='analyze_diffs_test_fail $in')
  n.rule('analyze_diffs_test_success',
         command=('if ! %s --under_test $in > $output_path 2>&1; then '
                  '  echo "Unexpected failure"; cat $output_path; exit 1; '
                  'elif [ -s $output_path ]; then '
                  '  echo "Succeeded but had unexpected output:"; '
                  '  cat $output_path; '
                  '  exit 1; '
                  'else '
                  '  touch $out; '
                  'fi' % script),
         description='analyze_diffs_test_success $in')
  all_mods = build_common.find_all_files([staging.TESTS_MODS_PATH],
                                         include_tests=True)
  out_dir = os.path.join(build_common.get_target_common_dir(),
                         'analyze_diff_tests')
  for f in all_mods:
    no_ext = os.path.splitext(f)[0]
    no_ext_relative = os.path.relpath(no_ext, staging.TESTS_MODS_PATH)
    out_path = os.path.join(out_dir, no_ext_relative)
    output_path = out_path + '.output'
    results_path = out_path + '.results'
    variables = {'output_path': output_path}

    rule = None
    if f.endswith('.fail'):
      rule = 'analyze_diffs_test_fail'
    elif f.endswith('.success'):
      rule = 'analyze_diffs_test_success'
    if rule is not None:
      n.build(results_path, rule, no_ext, variables=variables,
              implicit=[script], use_staging=False)


def _generate_checkdeps_ninjas():
  if open_source.is_open_source_repo():
    # Do not run checkdeps on the open source repo since some directories
    # checked are not included there.
    return
  n = NinjaGenerator('checkdeps', target_groups=['lint'])
  checkdeps_script = staging.as_staging(
      'android/external/chromium_org/tools/checkdeps/checkdeps.py')
  n.rule('checkdeps',
         command=('%s -v --root=$root $in_dir > $out.tmp 2>&1 '
                  '&& mv $out.tmp $out '
                  '|| (cat $out.tmp; rm $out.tmp; exit 1)' % checkdeps_script),
         description='checkdeps $in_dir')
  # Detect bad #include lines in src/.
  # TODO(crbug.com/323786): Check #include lines in mods/ too.
  src_dir = os.path.join(build_common.get_arc_root(), 'src')
  src_deps = os.path.join(src_dir, 'DEPS')
  for d in ['common', 'ndk_translation', 'posix_translation', 'wrap']:
    # TODO(crbug.com/323786): Check other directories in src/ too.
    implicit = build_common.find_all_files(
        os.path.join(src_dir, d),
        suffixes=['h', 'c', 'cc', 'cpp', 'java', 'DEPS'],
        include_tests=True, use_staging=False)
    implicit.extend([checkdeps_script, src_deps])
    out = os.path.join(build_common.OUT_DIR, 'checkdeps_%s.txt' % d)
    n.build(out, 'checkdeps', [],
            variables={'root': src_dir, 'in_dir': d},
            implicit=implicit)


def _generate_lint_ninjas():
  n = NinjaGenerator('lint', target_groups=['lint'])
  lint_script = 'src/build/lint_source.py'
  analyze_diffs_script = 'src/build/analyze_diffs.py'
  ignore = 'src/build/lint_ignore.txt'
  implicit_base = [analyze_diffs_script, lint_script, ignore]
  n.rule('lint', command=('%s -i %s -o $out $in' % (lint_script, ignore)),
         description='lint $out')
  n.rule('lint_merge', command='%s --merge -o $out @$out.rsp' % lint_script,
         rspfile='$out.rsp',
         rspfile_content='$in',
         description='lint --merge $out')

  files = lint_source.get_all_files_to_check()
  results = []
  for f in files:
    with ninja_generator.open_dependency(f, 'r',
                                         ignore_dependency=True) as source_file:
      tracking_path = analyze_diffs.compute_tracking_path(None, f, source_file)
      implicit = implicit_base[:]
      if tracking_path:
        implicit.append(tracking_path)
    out = os.path.join(build_common.OUT_DIR, 'lint', f + '.result')
    n.build(out, 'lint', f, implicit=implicit, use_staging=False)
    results.append(out)

  out = os.path.join(build_common.OUT_DIR, 'lint_results.txt')
  n.build(out, 'lint_merge', results, implicit=implicit_base, use_staging=False)


def _generate_disallowed_symbols_ninja():
  n = ninja_generator.NinjaGenerator('disallowed_symbols')
  out_path = os.path.join(build_common.get_build_dir(),
                          'gen_symbols', 'disallowed_symbols.defined')
  n.build([out_path], 'copy_symbols_file', 'src/build/disallowed_symbols.txt',
          implicit='src/build/symbol_tool.py')


def generate_binaries_depending_ninjas(_):
  if (not OPTIONS.is_nacl_x86_64() or
      not OPTIONS.is_optimized_build() or
      # None of the targets analyzed are currently built in the open source
      # repository.
      open_source.is_open_source_repo() or
      # Run the checker only when --disable-debug-code is specified. Locations
      # of static initializers differ depending on the debug-code option.
      OPTIONS.is_debug_code_enabled() or
      # The checker only works with debug symbols.
      not OPTIONS.is_debug_info_enabled()):
    # The static analysis tool's output varies between debug and non-debug
    # builds, so we pick non-debug as the default.
    return
  n = ninja_generator.NinjaGenerator('analyze_static_initializers')
  script = staging.as_staging(
      'android/external/chromium_org/tools/linux/dump-static-initializers.py')
  n.rule('analyze_static_initializers',
         command=('python %s -d $in | head --lines=-1 | '
                  'egrep -ve \'^# .*\.cpp \' |'
                  'sed -e \'s/ T\.[0-9]*/ T.XXXXX/\' |'
                  'diff -u $expect - && touch $out' %
                  script),
         description='analyze_static_initializers $in')
  libraries = build_common.CHECKED_LIBRARIES
  libraries_fullpath = [
      os.path.join(build_common.get_load_library_path(), lib)
      for lib in libraries]
  for library in zip(libraries, libraries_fullpath):
    # You can manually update the text files by running
    #   src/build/update_static_initializer_expectations.py.
    expect = 'src/build/dump-static-initializers-%s-expected.txt' % library[0]
    result_path = os.path.join(build_common.get_build_dir(),
                               'dump_static_initializers',
                               'dump_static_initializers.%s.result' %
                               library[0])
    n.build(result_path, 'analyze_static_initializers', library[1],
            variables={'out': result_path, 'expect': expect},
            # Add |libraries_fullpath| to implicit= not to run the analyzer
            # script until all libraries in |libraries_fullpath| become ready.
            # This makes it easy to use
            # update_static_initializer_expectations.py especially when you
            # remove global variables from two or more libraries at the same
            # time.
            implicit=[script, expect] + libraries_fullpath)


def _generate_check_symbols_ninja():
  # If we do not use NDK direct execution, the compatibility is less
  # important.
  if not build_common.use_ndk_direct_execution():
    return

  n = ninja_generator.NinjaGenerator('check_symbols')
  script = staging.as_staging('src/build/check_symbols.py')
  rule_name = 'check_symbols'
  n.rule(rule_name,
         command=('python %s $android_lib $in %s' % (
             script, build_common.get_test_output_handler())),
         description=(rule_name + ' $in'))

  assert OPTIONS.is_arm(), 'Only ARM supports NDK direct execution'
  arch_subdir = 'arch-arm'
  lib_dir = os.path.join(_ANDROID_SYSTEM_IMAGE_DIR, arch_subdir, 'usr/lib')
  for so_file in build_common.find_all_files(lib_dir, suffixes='.so'):
    lib_name = os.path.basename(so_file)
    if lib_name not in ['libc.so', 'libdl.so', 'libm.so']:
      # For now, we only check Bionic.
      # TODO(crbug.com/408548): Extend this for other libraries.
      continue
    result_path = os.path.join(build_common.get_build_dir(),
                               'check_symbols',
                               'check_symbols.%s.result' % lib_name)
    n.build(result_path, rule_name,
            build_common.get_build_path_for_library(lib_name),
            variables={'android_lib': staging.as_staging(so_file)},
            implicit=[script, staging.as_staging(so_file)])


def generate_ninjas():
  ninja_generator_runner.request_run_in_parallel(
      _generate_breakpad_ninja,
      _generate_check_symbols_ninja,
      _generate_checkdeps_ninjas,
      _generate_disallowed_symbols_ninja,
      _generate_lint_ninjas,
      _generate_test_framework_ninjas)


def generate_test_ninjas():
  if not open_source.is_open_source_repo():
    ninja_generator.generate_python_test_ninjas_for_path('src/build')
  ninja_generator_runner.request_run_in_parallel(
      _generate_lint_test_ninjas)
