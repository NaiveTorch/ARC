# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libchromium_base library for all of ARC."""

import os
import re

import build_common
import build_options
import ninja_generator


def _add_chromium_base_compiler_flags(n):
  n.add_libchromium_base_compile_flags()
  n.add_compiler_flags('-Wno-sign-compare', '-Werror')
  # This is needed because the sources related to message loop include jni.h.
  n.add_include_paths('android/libnativehelper/include/nativehelper',
                      'android/system/core/include')


def _generate_chromium_base_ninja():
  base_path = 'android/external/chromium_org/base'
  n = ninja_generator.ArchiveNinjaGenerator(
      'libchromium_base', base_path=base_path, instances=2)
  n.add_compiler_flags('-fvisibility=hidden')  # for libposix_translation.so
  _add_chromium_base_compiler_flags(n)

  def relevant(f):
    f = f.lstrip('android/external/chromium_org/')
    # Files with specific suffixes like '_linux' are usually excluded.
    # Here is the list of exceptions.
    whitelist = ['base/threading/platform_thread_linux.cc',
                 'base/debug/stack_trace_android.cc',
                 'base/debug/trace_event_android.cc']
    if f in whitelist:
      return True

    # Exclude cc files that do not compile with nacl-g++. Roughly speaking,
    # functions in the following categories do not compile/work:
    # - Functions that execute commands (e.g. *_xdg.cc).
    # - Functions that depends on file_util.h which is not (yet) available.
    excludes = [
        'base/allocator/generic_allocators.cc',
        'base/async_socket_io_handler_posix.cc',
        'base/base64.cc',
        'base/base_paths.cc',
        'base/base_paths_posix.cc',
        'base/check_example.cc',
        'base/cpu.cc',
        'base/debug_message.cc',
        # This is excluded in the upstream, too.
        'base/debug/stack_trace_posix.cc',
        'base/debug/trace_event_system_stats_monitor.cc',
        'base/files/file_enumerator_posix.cc',
        'base/files/file_proxy.cc',
        'base/files/important_file_writer.cc',
        'base/files/memory_mapped_file.cc',
        'base/files/scoped_temp_dir.cc',
        'base/guid_posix.cc',
        'base/json/json_file_value_serializer.cc',
        'base/memory/discardable_memory.cc',
        'base/memory/shared_memory_posix.cc',
        'base/message_loop/message_pump_ozone.cc',
        'base/message_loop/message_pump_x11.cc',
        'base/nix/mime_util_xdg.cc',
        'base/nix/xdg_util.cc',
        # This provides timegm implementation, but we use the one in bionic.
        'base/os_compat_nacl.cc',
        'base/path_service.cc',
        'base/perftimer.cc',
        'base/rand_util.cc',
        'base/rand_util_nacl.cc',
        'base/rand_util_posix.cc',
        'base/sync_socket_posix.cc',
        'base/third_party/dmg_fp/dtoa_wrapper.cc',
        'base/threading/watchdog.cc',
        'base/x11/edid_parser_x11.cc',
        'base/x11/x11_error_tracker.cc']
    if ((f in excludes) or
        # Exclude non-cc files.
        (not f.endswith('.cc') and not f.endswith('.c')) or
        # Exclude tests.
        re.search(r'test?\.cc|unittest|/test/', f) or
        # Exclude directories that are not compatible with nacl-g++.
        re.search(r'/(i18n|prefs|histogram|metrics|xdg_mime|process)/', f) or
        # Exclude files for other architectures. Also excludes files that
        # operates files. These files do not seem to support OS_NACL build.
        re.search(r'[/_](win|mac|linux|chromeos|android|ios|glib|gtk|'
                  'openbsd|freebsd|kqueue|libevent|aurax11|'
                  # TODO(yusukes): Try to compile file_util*.cc with NaCl g++
                  #                to minimize the |excludes| list above.
                  'sys_info|process_|shim|file_util)', f)):
      return False
    return True

  build_files = filter(relevant, n.find_all_sources())
  n.build_default(build_files, base_path=None).archive()

  # Dump global symbols in libchromium_base.
  out_path = os.path.join(ninja_generator.CNinjaGenerator.get_symbols_path(),
                          'libchromium_base.a.defined')
  n.build([out_path], 'dump_defined_symbols',
          build_common.get_build_path_for_library('libchromium_base.a'),
          implicit='src/build/symbol_tool.py')


def _generate_chromium_base_test_ninja():
  base_path = 'android/external/chromium_org'
  n = ninja_generator.TestNinjaGenerator('libchromium_base_test',
                                         base_path=base_path)
  _add_chromium_base_compiler_flags(n)

  # For third_party/testing/gmock. chromium_org/base/*_test.cc include gmock
  # files with '#include "testing/gmock/...".
  n.add_include_paths('out/staging')

  n.add_compiler_flags('-DUNIT_TEST')  # for base/at_exit.h

  # TODO(crbug.com/239062): Support DEATH_TEST on Linux and enable these tests.
  #   'base/memory/weak_ptr_unittest.cc'
  #   'base/synchronization/cancellation_flag_unittest.cc'
  test_files = [
      'base/at_exit_unittest.cc',
      'base/atomicops_unittest.cc',
      'base/bits_unittest.cc',
      'base/files/file_path_unittest.cc',
      'base/id_map_unittest.cc',
      'base/json/json_parser_unittest.cc',
      'base/json/json_value_converter_unittest.cc',
      'base/json/string_escape_unittest.cc',
      'base/md5_unittest.cc',
      'base/memory/linked_ptr_unittest.cc',
      'base/memory/ref_counted_memory_unittest.cc',
      'base/memory/ref_counted_unittest.cc',
      'base/memory/scoped_ptr_unittest.cc',
      'base/memory/scoped_vector_unittest.cc',
      'base/memory/singleton_unittest.cc',
      'base/safe_numerics_unittest.cc',
      'base/scoped_clear_errno_unittest.cc',
      'base/sha1_unittest.cc',
      'base/stl_util_unittest.cc',
      'base/strings/string16_unittest.cc',
      'base/strings/string_number_conversions_unittest.cc',
      'base/strings/string_piece_unittest.cc',
      'base/strings/string_split_unittest.cc',
      'base/strings/string_tokenizer_unittest.cc',
      'base/strings/string_util_unittest.cc',
      'base/strings/stringize_macros_unittest.cc',
      'base/strings/stringprintf_unittest.cc',
      'base/strings/utf_offset_string_conversions_unittest.cc',
      'base/strings/utf_string_conversions_unittest.cc',
      'base/template_util_unittest.cc',
      'base/time/time_unittest.cc',
      'base/tuple_unittest.cc',
      'base/values_unittest.cc',
      'libchromium_base_test_main.cc']  # main function
  if not build_options.OPTIONS.is_nacl_build():
    test_files.extend(['base/environment_unittest.cc'])
  if not build_options.OPTIONS.is_arm():
    # qemu-arm does not support threading at this point.
    test_files.extend(['base/lazy_instance_unittest.cc',
                       'base/synchronization/condition_variable_unittest.cc',
                       'base/synchronization/lock_unittest.cc',
                       'base/synchronization/waitable_event_unittest.cc'])
  test_files = [os.path.join(base_path, f) for f in test_files]
  n.build_default(test_files, base_path=None)
  # Exclude FilePathTest.FromUTF8Unsafe_And_AsUTF8Unsafe since the test
  # indirectly depends on base/strings/sys_string_conversions_posix.cc which in
  # turn calls functions like ::wcrtomb() to convert a std::wstring to a system
  # locale's multi byte one. For Linux build, we could make such MB/WC function
  # work by calling ::setlocale(LC_ALL, "en_US.utf8") in the main function, but
  # for NaCl, we have no way.
  exclude = ['FilePathTest.FromUTF8Unsafe_And_AsUTF8Unsafe']
  # Exclude TimeTest.FromLocalExplodedCrashOnAndroid for now because the test
  # relies on timezone info, which is located at
  # '/system/usr/share/zoneinfo/tzdata' in the readonly filesystem, but we do
  # not have an easy way to access this data from unit tests.
  exclude.append('TimeTest.FromLocalExplodedCrashOnAndroid')
  # Positional parameter of printf in bionic is currently broken.
  # TODO(crbug.com/248851): Fix this.
  exclude.append('StringPrintfTest.PositionalParameters')
  n.run(n.link(), '--gtest_filter=\'-%s\'' % ':'.join(exclude))


def generate_ninjas():
  _generate_chromium_base_ninja()


def generate_test_ninjas():
  _generate_chromium_base_test_ninja()
