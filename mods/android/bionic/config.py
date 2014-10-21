#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#

import os
import re
import string

import build_common
import make_to_ninja
import ninja_generator
import ninja_generator_runner
import staging
import toolchain
from build_options import OPTIONS
from make_to_ninja import Filters
from make_to_ninja import MakefileNinjaTranslator


_LOADER_TEXT_SECTION_START_ADDRESS = '0x20000'

# TODO(crbug.com/315954): Enable more Cortex-A15 *.S files once we get -t=ba
# (Bare Metal ARM) configuration.
_ARM_ASM_FILES = ['android/bionic/libc/arch-arm/bionic/memcmp16.S']

# TODO(crbug.com/315954): Enable more i686 *.S files.
_I686_ASM_FILES = ['android/bionic/libc/arch-x86/string/bzero.S',
                   'android/bionic/libc/arch-x86/string/sse2-strchr-atom.S']


def _add_bare_metal_flags_to_make_to_ninja_vars(vars):
  if ((vars.is_c_library() or vars.is_executable()) and
      OPTIONS.is_bare_metal_build()):
    vars.get_asmflags().append('-DBARE_METAL_BIONIC')
    vars.get_cflags().append('-DBARE_METAL_BIONIC')
    vars.get_cxxflags().append('-DBARE_METAL_BIONIC')


def _add_bare_metal_flags_to_ninja_generator(n):
  if OPTIONS.is_bare_metal_build():
    n.add_defines('BARE_METAL_BIONIC')


def _get_gen_source_dir():
  return os.path.join(build_common.get_build_dir(), 'bionic_gen_sources')


def _get_gen_source_stamp():
  # We create this file after all assembly files are generated. We can
  # save the size of a ninja file by depending on this stamp file
  # instead of all generated assembly files. Without this proxy file,
  # the ninja file for libc_common.a will be about 3 times bigger.
  return os.path.join(_get_gen_source_dir(), 'STAMP')


def _get_asm_source(f):
  # For NaCl, we need to use naclized version of aseembly code.
  if OPTIONS.is_nacl_build():
    f = os.path.join(_get_gen_source_dir(), os.path.basename(f))
  return f


def _remove_assembly_source(sources):
  asm_sources = filter(lambda s: s.endswith('.S'), sources)
  for asm in asm_sources:
    sources.remove(asm)


def _generate_naclized_asm_ninja(ninja_name, rule_name,
                                 script_path, asm_files):
  n = ninja_generator.NinjaGenerator(ninja_name)
  # NaClize *.S files and write them as bionic_gen_sources/*.S.
  script_path = staging.as_staging(script_path)
  n.rule(rule_name,
         command=('python %s $in > $out' % script_path),
         description=rule_name + ' $out')
  all_generated_files = []
  for f in asm_files:
    outputs = [os.path.join(_get_gen_source_dir(), os.path.basename(f))]
    n.build(outputs, rule_name, staging.as_staging(f), implicit=script_path)
    all_generated_files += outputs

  rule_name += '_stamp'
  n.rule(rule_name, command='touch $out', description=rule_name + ' $out')
  n.build(_get_gen_source_stamp(), rule_name, all_generated_files)


def _generate_naclized_i686_asm_ninja():
  if not OPTIONS.is_nacl_i686():
    return
  _generate_naclized_asm_ninja('bionic_gen_i686_asm_sources',
                               'gen_naclized_i686_file_bionic',
                               'src/build/naclize_i686.py',
                               _I686_ASM_FILES)


def _filter_libc_common_for_arm(vars, sources):
  for f in _ARM_ASM_FILES:
    sources.append(_get_asm_source(f))
  if OPTIONS.is_bare_metal_build():
    # For direct syscalls used internally.
    sources.append('android/bionic/libc/arch-arm/bionic/syscall.S')
  else:
    # Order-only dependency should be sufficient for this case
    # because all dependencies should be handled properly once .d
    # files are generated. However, we have a strict check for
    # order-only dependencies (see NinjaGenerator._check_deps)
    # so we use implicit dependencies here for now. As we do not
    # update assembly code often, this will not harm our iteration
    # cycle much.
    # TODO(crbug.com/318433): Use order-only dependencies.
    vars.get_implicit_deps().append(_get_gen_source_stamp())
  # TODO(crbug.com/352917): Replace them with memset.S for Cortex A15.
  sources.extend(['android/bionic/libc/string/bzero.c',
                  'android/bionic/libc/string/strcpy.c',
                  'nacl-newlib/newlib/libc/string/memset.c'])


def _filter_libc_common_for_i686(vars, sources):
  for f in _I686_ASM_FILES:
    sources.append(_get_asm_source(f))
  if OPTIONS.is_bare_metal_i686() and OPTIONS.enable_valgrind():
    # SSE2 strchr may access address before the passed string when the
    # string is not 16-byte aligned and valgrind complains.
    sources.remove('android/bionic/libc/arch-x86/string/sse2-strchr-atom.S')
    sources.append('android/bionic/libc/bionic/strchr.cpp')
  if OPTIONS.is_bare_metal_build():
    # For direct syscalls used internally.
    sources.append('android/bionic/libc/arch-x86/bionic/syscall.S')
  else:
    # See the comment in _filter_libc_common_for_arm.
    # TODO(crbug.com/318433): Use order-only dependencies.
    vars.get_implicit_deps().append(_get_gen_source_stamp())
  # It seems newlib's memset is slightly faster than the
  # assembly implementation (0.16[sec/GB] vs 0.19[sec/GB]).
  sources.append('nacl-newlib/newlib/libc/string/memset.c')
  # This file contains inline assembly.
  sources.remove('android/bionic/libc/arch-x86/bionic/__set_tls.c')
  # TODO(crbug.com/268485): Confirm ARC can ignore non-SSSE3 x86 devices
  vars.get_cflags().append('-DUSE_SSSE3=1')


def _filter_libc_common_for_x86_64(vars, sources):
  sources.extend(['android/bionic/libc/string/bzero.c',
                  'android/bionic/libc/bionic/strchr.cpp',
                  # Newlib's memset is much faster than Bionic's
                  # memset.c. (0.13[sec/GB] vs 0.51[sec/GB])
                  'nacl-newlib/newlib/libc/string/memset.c'])
  # This file contains inline assembly.
  sources.remove('android/bionic/libc/arch-x86/bionic/__set_tls.c')


def _remove_unnecessary_defines(vars):
  """Cleans up unnecessary C/C++ defines."""
  # We always use hard-float.
  vars.remove_c_or_cxxflag('-DSOFTFLOAT')
  # Remove debug related macros since they should be controlled by
  # ./configure.
  vars.remove_c_or_cxxflag('-DNDEBUG')
  vars.remove_c_or_cxxflag('-UDEBUG')


def _filter_libc_common(vars):
  sources = vars.get_sources()
  _remove_assembly_source(sources)
  # libc_common is used from both the loader and libc.so. Functions
  # which are necessary for the bionic loader must be in this list.
  sources.extend([
      # TODO(crbug.com/243244): If possible, move arch-nacl/ files into a
      # separate archive and build them with -Werror.
      'android/bionic/libc/arch-nacl/bionic/__get_sp.c',
      'android/bionic/libc/arch-nacl/bionic/__set_tls.c',
      'android/bionic/libc/arch-nacl/bionic/clone.c',
      'android/bionic/libc/arch-nacl/bionic/popcount.c',
      'android/bionic/libc/arch-nacl/syscalls/__getcwd.c',
      'android/bionic/libc/arch-nacl/syscalls/__open.c',
      'android/bionic/libc/arch-nacl/syscalls/_exit.c',
      'android/bionic/libc/arch-nacl/syscalls/_exit_thread.c',
      'android/bionic/libc/arch-nacl/syscalls/clock_getres.c',
      'android/bionic/libc/arch-nacl/syscalls/clock_gettime.c',
      'android/bionic/libc/arch-nacl/syscalls/close.c',
      'android/bionic/libc/arch-nacl/syscalls/dup.c',
      'android/bionic/libc/arch-nacl/syscalls/dup2.c',
      'android/bionic/libc/arch-nacl/syscalls/enosys.c',
      'android/bionic/libc/arch-nacl/syscalls/fdatasync.c',
      'android/bionic/libc/arch-nacl/syscalls/fstat.c',
      'android/bionic/libc/arch-nacl/syscalls/fsync.c',
      'android/bionic/libc/arch-nacl/syscalls/futex.c',
      'android/bionic/libc/arch-nacl/syscalls/getdents.c',
      'android/bionic/libc/arch-nacl/syscalls/getpid.c',
      'android/bionic/libc/arch-nacl/syscalls/gettid.c',
      'android/bionic/libc/arch-nacl/syscalls/gettimeofday.c',
      'android/bionic/libc/arch-nacl/syscalls/getuid.c',
      'android/bionic/libc/arch-nacl/syscalls/lseek.c',
      'android/bionic/libc/arch-nacl/syscalls/lseek64.c',
      'android/bionic/libc/arch-nacl/syscalls/lstat.c',
      'android/bionic/libc/arch-nacl/syscalls/mmap.c',
      'android/bionic/libc/arch-nacl/syscalls/mprotect.c',
      'android/bionic/libc/arch-nacl/syscalls/munmap.c',
      'android/bionic/libc/arch-nacl/syscalls/nacl_stat.c',
      'android/bionic/libc/arch-nacl/syscalls/nacl_timespec.c',
      'android/bionic/libc/arch-nacl/syscalls/nacl_timeval.c',
      'android/bionic/libc/arch-nacl/syscalls/read.c',
      'android/bionic/libc/arch-nacl/syscalls/stat.c',
      'android/bionic/libc/arch-nacl/syscalls/unlink.c',
      'android/bionic/libc/arch-nacl/syscalls/write.c',
      'android/bionic/libc/arch-nacl/syscalls/writev.c',
      'android/bionic/libc/arch-nacl/tmp/raw_print.c',
      # TODO(crbug.com/352917): Use assembly version on Bare Metal ARM.
      'android/bionic/libc/bionic/memcmp.c',
      'android/bionic/libc/bionic/memcpy.c',
      'android/bionic/libc/bionic/property_service.c',
      'android/bionic/libc/string/ffs.c',
      'android/bionic/libc/string/strcat.c',
      'android/bionic/libc/string/strcmp.c',
      'android/bionic/libc/string/strlen.c'])
  if OPTIONS.is_nacl_build():
    # They define SFI NaCl specific functions for dynamic code.
    sources.extend([
        'android/bionic/libc/arch-nacl/syscalls/__allocate_nacl_dyncode.c',
        'android/bionic/libc/arch-nacl/syscalls/nacl_dyncode_create.c',
        'android/bionic/libc/arch-nacl/syscalls/nacl_dyncode_delete.c',
        'android/bionic/libc/arch-nacl/syscalls/nacl_list_mappings.c'])

  if OPTIONS.is_arm():
    # TODO(crbug.com/352917): Use assembly version on Bare Metal ARM.
    sources.extend([
        'android/bionic/libc/bionic/__memcpy_chk.cpp',
        'android/bionic/libc/bionic/__memset_chk.cpp',
        'android/bionic/libc/bionic/__strcat_chk.cpp',
        'android/bionic/libc/bionic/__strcpy_chk.cpp'])
  else:
    sources.extend([
        'android/bionic/libc/bionic/memchr.c',
        'android/bionic/libc/bionic/memrchr.c',
        'android/bionic/libc/bionic/memmove.c',
        'android/bionic/libc/bionic/strnlen.c',
        'android/bionic/libc/string/bcopy.c',
        'android/bionic/libc/string/index.c',
        'android/bionic/libc/string/strncmp.c',
        'android/bionic/libc/string/strrchr.c',
        'android/bionic/libc/upstream-freebsd/lib/libc/string/wcschr.c',
        'android/bionic/libc/upstream-freebsd/lib/libc/string/wcsrchr.c',
        'android/bionic/libc/upstream-freebsd/lib/libc/string/wcscmp.c',
        'android/bionic/libc/upstream-freebsd/lib/libc/string/wcslen.c'])

  if OPTIONS.is_arm():
    _filter_libc_common_for_arm(vars, sources)
  elif OPTIONS.is_i686():
    _filter_libc_common_for_i686(vars, sources)
  elif OPTIONS.is_x86_64():
    _filter_libc_common_for_x86_64(vars, sources)

  # NaCl does not have fork so we do not need the fork wrapper
  # which does preparation before we actually run fork system call.
  sources.remove('android/bionic/libc/bionic/fork.c')
  # lseek64 in this file splits off64_t into two integer values to
  # make assembly code easier. We can define lseek64 in C so we do
  # not need this wrapper.
  sources.remove('android/bionic/libc/bionic/lseek64.c')
  if OPTIONS.is_x86_64() or OPTIONS.is_bare_metal_i686():
    # We define __get_tls in nacl_read_tp.c.
    sources.remove('android/bionic/libc/arch-x86/bionic/__get_tls.c')
  if (OPTIONS.is_arm() or OPTIONS.is_x86_64() or
      OPTIONS.is_bare_metal_build()):
    sources.append('android/bionic/libc/arch-nacl/bionic/nacl_read_tp.c')
  vars.get_includes().append('android/bionic/libc/arch-nacl/syscalls')
  _remove_unnecessary_defines(vars)
  vars.get_cflags().append('-ffunction-sections')
  vars.get_cflags().append('-fdata-sections')
  return True


def _filter_libc_netbsd(vars):
  # This library has some random functions grabbed from
  # NetBSD. Functions defined in this library includes file tree
  # functions (ftw and nftw), signal printers (e.g., psignal),
  # regexp functions (e.g., regcomp), binary tree functions (e.g.,
  # twalk), creat, nice, and strxfrm.
  vars.remove_c_or_cxxflag('-w')
  # libc/upstream-netbsd/netbsd-compat.h defines _GNU_SOURCE for you.
  vars.remove_c_or_cxxflag('-D_GNU_SOURCE')
  vars.get_cflags().append('-Wno-implicit-function-declaration')
  vars.get_cflags().append('-Wno-sign-compare')
  vars.get_cflags().append('-W')
  vars.get_cflags().append('-Werror')
  _remove_unnecessary_defines(vars)
  return True


def _filter_libc_bionic(vars):
  # TODO(yusukes): Try to use -Werror.
  sources = vars.get_sources()
  # NaCl does not support signals.
  sources.remove('android/bionic/libc/bionic/pthread_kill.cpp')
  sources.remove('android/bionic/libc/bionic/pthread_sigmask.cpp')
  # Bionic's mmap is a wrapper for __mmap2. Works the wrapper does
  # are not necessary for NaCl and it calls madvice, which NaCl
  # does not support. We will simply define mmap without the wrapper.
  sources.remove('android/bionic/libc/bionic/mmap.cpp')
  return True


def _filter_libc(vars):
  if vars.is_static():
    return False

  vars.get_sources().remove('android/bionic/libc/bionic/pthread_debug.cpp')
  vars.get_sources().extend([
      'android/bionic/libc/arch-nacl/bionic/atexit.c',
      'android/bionic/libc/arch-nacl/syscalls/clock_nanosleep.c',
      'android/bionic/libc/arch-nacl/syscalls/irt_syscalls.c',
      'android/bionic/libc/arch-nacl/syscalls/nanosleep.c',
      'android/bionic/libc/arch-nacl/syscalls/sched_yield.c',
      'android/bionic/libc/arch-nacl/tmp/libc_stubs.c',
      'android/bionic/libc/string/rindex.c'
  ])
  if OPTIONS.is_i686():
    vars.get_sources().append(
        'android/bionic/libc/arch-x86/bionic/setjmp.S')
  if OPTIONS.is_x86_64():
    vars.get_sources().append(
        'android/bionic/libc/arch-amd64/bionic/setjmp.S')
    vars.get_includes().insert(0, 'android/bionic/libc/arch-amd64/include')
  if OPTIONS.is_arm():
    vars.get_sources().append(
        'android/bionic/libc/arch-arm/bionic/setjmp.S')
    # Remove the sources that contain the functions we implement.
    vars.get_sources().remove(
        'android/bionic/libc/arch-arm/bionic/atexit_legacy.c')
    if OPTIONS.is_bare_metal_build():
      # TODO(crbug.com/319020): Use Bare Metal IRT instead of
      # calling a syscall directly.
      vars.get_sources().extend([
          'android/bionic/libc/arch-arm/bionic/_setjmp.S',
          'android/bionic/libc/arch-arm/bionic/sigsetjmp.S',
          'android/bionic/libc/arch-nacl/syscalls/cacheflush.c'])
  vars.get_includes().append('android/bionic/libc/arch-nacl/syscalls')
  vars.get_implicit_deps().extend([build_common.get_bionic_crtbegin_so_o(),
                                   build_common.get_bionic_crtend_o()])
  # This looks weird libc depends on libdl, but the upstream
  # bionic also does the same thing. Note that libdl.so just has
  # stub functions and their actual implementations are in the
  # loader (see third_party/android/bionic/linker/dlfcn.c).
  vars.get_shared_deps().append('libdl')
  vars.get_whole_archive_deps().append('libc_bionic')
  vars.get_whole_archive_deps().append('libc_freebsd')
  vars.get_whole_archive_deps().append('libc_netbsd')
  # We do not support stack protector on NaCl, but NDK may require a
  # symbol in this file. So, we always link this.
  vars.get_whole_archive_deps().append('libbionic_ssp')
  vars.get_whole_archive_deps().append('libc_tzcode')
  # Let dlmalloc not use sbrk as NaCl Bionic does not provide brk/sbrk.
  vars.get_cflags().append('-DHAVE_MORECORE=0')
  _remove_unnecessary_defines(vars)
  if OPTIONS.is_arm():
    # libc/upstream-dlmalloc/malloc.c checks "linux" to check if
    # mremap is available, which we do not have. We need this fix
    # only for Bare Metal ARM because NaCl toolchain does not
    # define "linux" and Android undefines "linux" by default for
    # x86 (android/build/core/combo/TARGET_linux-x86.mk).
    vars.get_cflags().append('-Ulinux')
  vars.get_generator_args()['is_system_library'] = True
  if OPTIONS.is_arm():
    # Set False to 'link_crtbegin' because Android.mk for libc.so
    # compiles android/bionic/libc/arch-arm/bionic/crtbegin_so.c by
    # default with -DCRT_LEGACY_WORKAROUND to export the __dso_handle
    # symbol.
    #
    # __dso_handle is passed to __cxa_atexit so that libc knows which
    # atexit handler belongs to which module. In general, __dso_handle
    # should be a private symbol. Otherwise, a module (say A) can
    # depend on __dso_handle in another module (B), and the atexit
    # handler in A will not be called when the module A is unloaded.
    #
    # However, it seems the old version of Android had a bug and
    # __dso_handle was exposed. Several NDKs depend on __dso_handle
    # in libc.so. To execute such binaries directly, we need to define
    # a public __dso_handle, too. This effectively means atexit
    # handlers in such NDKs will never be called, as we will never
    # unload libc.so. This is a known upstream issue. See
    # third_party/android/bionic/ABI-bugs.txt.
    #
    # Note it is OK not to have crtbegin_so.o as the first object when
    # we link libc.so because we are using init_array/fini_array,
    # which do not require specific watchdogs, for ARM.
    vars.get_generator_args()['link_crtbegin'] = False
  return True


def _filter_libc_malloc_debug_leak(vars):
  if vars.is_static():
    return False
  # This module should not be included for --opt --disable-debug-code,
  # and it is controlled by TARGET_BUILD_VARIANT in the Android.mk.
  assert OPTIONS.is_debug_code_enabled()
  # libc_malloc_debug_leak.so should not use lib_common.a. See comments
  # above.
  vars.get_whole_archive_deps().remove('libc_common')
  vars.get_shared_deps().append('libdl')
  # Linking libc.so instead of libc_logging.cpp does not work because
  # __libc_format_* functions in the file are __LIBC_HIDDEN.
  vars.get_sources().append(
      'android/bionic/libc/bionic/libc_logging.cpp')
  _remove_unnecessary_defines(vars)
  vars.get_generator_args()['is_system_library'] = True
  return True


def _filter_libc_freebsd(vars):
  return True


def _filter_libc_tzcode(vars):
  # TODO(yusukes): Try to use -Werror.
  return True


def _filter_libbionic_ssp(vars):
  # Used by both libc.so and runnable-ld.so.
  vars.set_instances_count(2)
  return True


def _filter_tzdata(vars):
  vars.set_prebuilt_install_to_root_dir(True)
  return True


def _dispatch_libc_sub_filters(vars):
  # Any libraries/executables except libc.so and the loader should *NEVER*
  # be linked into libc_common because libc_common has global variables
  # which require proper initialization (e.g. IRT function pointers in
  # irt_syscalls.c).
  # TODO(crbug.com/243244): Consider using -Wsystem-headers.
  return {
      'libc_common': _filter_libc_common,
      'libc_netbsd': _filter_libc_netbsd,
      'libc_freebsd': _filter_libc_freebsd,
      'libc_tzcode': _filter_libc_tzcode,
      'libc_bionic': _filter_libc_bionic,
      'libc': _filter_libc,
      'libc_malloc_debug_leak': _filter_libc_malloc_debug_leak,
      'libbionic_ssp': _filter_libbionic_ssp,
      'tzdata': _filter_tzdata,
  }.get(vars.get_module_name(), lambda vars: False)(vars)


def _generate_libc_ninja():
  def _filter(vars, is_for_linker=False):
    if not _dispatch_libc_sub_filters(vars):
      return False

    _add_bare_metal_flags_to_make_to_ninja_vars(vars)
    if is_for_linker:
      module_name = vars.get_module_name()
      # We only need these three modules.
      if module_name not in ['libc_bionic', 'libc_common', 'libc_freebsd']:
        return False
      vars.set_module_name(module_name + '_linker')
      # The loader does not need to export any symbols.
      vars.get_cflags().append('-fvisibility=hidden')
      vars.get_cxxflags().append('-fvisibility=hidden')
      # We need to control the visibility using GCC's pragma based on
      # this macro. See bionic/libc/arch-nacl/syscalls/irt_syscalls.h.
      vars.get_cflags().append('-DBUILDING_LINKER')
      vars.get_cxxflags().append('-DBUILDING_LINKER')
    return True

  MakefileNinjaTranslator('android/bionic/libc').generate(
      lambda vars: _filter(vars, is_for_linker=False))
  MakefileNinjaTranslator('android/bionic/libc').generate(
      lambda vars: _filter(vars, is_for_linker=True))


def _generate_libm_ninja():
  def _filter(vars):
    if vars.is_shared():
      return False
    make_to_ninja.Filters.convert_to_shared_lib(vars)
    _add_bare_metal_flags_to_make_to_ninja_vars(vars)
    # Builtin rint and rintf call lrint and lrintf,
    # respectively. However, Bionic calls rint and rintf to implement
    # lrint and lrintf and this causes an infinite recurision.
    # TODO(crbug.com/357564): Change this to -fno-builtin.
    vars.get_cflags().append('-fno-builtin-rint')
    vars.get_cflags().append('-fno-builtin-rintf')
    sources = vars.get_sources()
    _remove_assembly_source(sources)
    if OPTIONS.is_arm():
      vars.get_includes().append('android/bionic/libc/arch-arm/include')
    else:
      # TODO(crbug.com/414583): "L" has arch-x86_64 directory so we
      # should have this include path only for i686 targets.
      vars.get_includes().append('android/bionic/libc/arch-x86/include')
      if OPTIONS.is_x86_64():
        vars.get_includes().insert(0, 'android/bionic/libc/arch-amd64/include')
        sources.remove(
            'android/bionic/libm/upstream-freebsd/lib/msun/src/e_sqrtf.c')
        sources.remove('android/bionic/libm/i387/fenv.c')
        sources.extend(['android/bionic/libm/amd64/e_sqrtf.S',
                        'android/bionic/libm/amd64/fenv.c'])
    if OPTIONS.is_bare_metal_i686():
      # long double is double on other architectures. For them,
      # s_nextafter.c defines nextafterl.
      sources.append(
          'android/bionic/libm/upstream-freebsd/lib/msun/src/s_nextafterl.c')
    vars.get_generator_args()['is_system_library'] = True
    vars.get_shared_deps().append('libc')
    return True

  MakefileNinjaTranslator('android/bionic/libm').generate(_filter)


def _generate_libdl_ninja():
  def _filter(vars):
    _add_bare_metal_flags_to_make_to_ninja_vars(vars)
    vars.get_implicit_deps().extend([build_common.get_bionic_crtbegin_so_o(),
                                     build_common.get_bionic_crtend_so_o()])
    vars.remove_c_or_cxxflag('-w')
    vars.get_cflags().append('-W')
    vars.get_cflags().append('-Werror')
    vars.get_generator_args()['is_system_library'] = True
    return True

  MakefileNinjaTranslator('android/bionic/libdl').generate(_filter)


# The "fundamental test" tests the features of the loader and the
# initialization process of libc. As we may want to test various kinds
# of objects with various kinds of setup, you can specify any command
# to build and test them. If you can use googletest, you should add
# tests to normal bionic_test instead (mods/android/bionic/tests).
class BionicFundamentalTest(object):
  ALL_OUTPUT_BINARIES = []

  @staticmethod
  def _get_src_dir():
    return staging.as_staging('android/bionic/tests/fundamental')

  @staticmethod
  def _get_out_dir():
    return os.path.join(build_common.get_build_dir(), 'bionic_tests')

  def __init__(self, test_binary_name, inputs, output, build_commands):
    self._test_binary_name = test_binary_name
    self._build_commands = build_commands
    out = os.path.join(BionicFundamentalTest._get_out_dir(), test_binary_name)
    asmflags = ninja_generator.CNinjaGenerator.get_archasmflags()
    if OPTIONS.is_bare_metal_build():
      asmflags += ' -DBARE_METAL_BIONIC '
    cflags = ninja_generator.CNinjaGenerator.get_archcflags()
    cxxflags = ninja_generator.CNinjaGenerator.get_cxxflags()
    cflags = asmflags + cflags + ' $commonflags -g -fPIC -Wall -W -Werror '
    cxxflags = cflags + cxxflags
    ldflags = ('-Wl,-rpath-link=' + build_common.get_load_library_path() +
               ' -Wl,--hash-style=sysv')
    # Use -Bsymbolic to have similar configuration as other NaCl
    # executables in ARC.
    soflags = '-shared -Wl,-Bsymbolic'
    if OPTIONS.is_arm():
      # For ARM, we need to link libgcc.a into shared objects. See the comment
      # in SharedObjectNinjaGenerator.
      # TODO(crbug.com/283798): Build libgcc by ourselves and remove this.
      soflags += ' ' + ' '.join(
          ninja_generator.get_libgcc_for_bionic())
    text_segment_address = (ninja_generator.ExecNinjaGenerator.
                            get_nacl_text_segment_address())
    if OPTIONS.is_bare_metal_build():
      execflags = '-pie'
      # Goobuntu's linker emits RWX pages for small PIEs. Use gold
      # instead. We cannot specify -fuse-ld=gold. As we are building
      # executables directly from .c files, the -fuse-ld flag will be
      # passed to cc1 and it does not recognize this flag.
      ldflags += ' -Bthird_party/gold'
    else:
      # This is mainly for ARM. See src/build/ninja_generator.py for detail.
      execflags = '-Wl,-Ttext-segment=' + text_segment_address
    self._variables = {
        'name': self._test_binary_name,
        'cc': toolchain.get_tool(OPTIONS.target(), 'cc'),
        'cxx': toolchain.get_tool(OPTIONS.target(), 'cxx'),
        'lib_dir': build_common.get_load_library_path(),
        'in_dir': BionicFundamentalTest._get_src_dir(),
        'out_dir': BionicFundamentalTest._get_out_dir(),
        'out': out,
        'crtbegin_exe': build_common.get_bionic_crtbegin_o(),
        'crtbegin_so': build_common.get_bionic_crtbegin_so_o(),
        'crtend_exe': build_common.get_bionic_crtend_o(),
        'crtend_so': build_common.get_bionic_crtend_so_o(),
        'cflags': cflags,
        'cxxflags': cxxflags,
        'ldflags': ldflags,
        'soflags': soflags,
        'execflags': execflags
    }
    self._inputs = map(self._expand_vars, inputs)
    self._output = self._expand_vars(output)

  def _expand_vars(self, s):
    return string.Template(s).substitute(self._variables)

  def emit(self, n):
    BionicFundamentalTest.ALL_OUTPUT_BINARIES.append(self._output)

    rule_name = 'build_bionic_' + self._test_binary_name
    commands = []
    for command in self._build_commands:
      assert command
      command = self._expand_vars(' '.join(command))
      commands.append(command)
    n.rule(rule_name, command=' && '.join(commands),
           description=rule_name + ' $in')
    n.build(self._output, rule_name, self._inputs,
            implicit=build_common.get_bionic_objects(need_stlport=False))


def _generate_bionic_fundamental_tests():
  n = ninja_generator.NinjaGenerator('bionic_fundamental_tests')
  bionic_tests = []
  if OPTIONS.is_nacl_build():
    # This uses NaCl syscalls directly and is not compatible with Bare
    # Metal mode.
    bionic_tests.append(
        BionicFundamentalTest(
            'loader_test', ['$in_dir/$name.c'], '$out',
            [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
              '-L$lib_dir', '-lc'] +
             ninja_generator.get_libgcc_for_bionic() +
             ['-ldl', '$$in', '-o', '$$out']]))
  bionic_tests.extend([
      BionicFundamentalTest(
          'write_test', ['$in_dir/$name.c'], '$out',
          [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$$in', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'printf_test', ['$in_dir/$name.c'], '$out',
          [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$$in', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'args_test', ['$in_dir/$name.c'], '$out',
          [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$$in', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'structors_test', ['$in_dir/$name.c'], '$out',
          [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$$in', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'resolve_parent_sym_test',
          ['$in_dir/$name.c',
           '$in_dir/${name}_first.c', '$in_dir/${name}_second.c'],
          '$out',
          [['$cc', '$cflags', '$ldflags', '-nostdlib',
            '$crtbegin_so', '-L$lib_dir', '-lc',
            '$in_dir/${name}_second.c', '$crtend_so',
            '$soflags', '-o', '$out_dir/lib${name}_second.so'],
           ['$cc', '$cflags', '$ldflags', '-nostdlib',
            '-L$out_dir', '-l${name}_second',
            '$crtbegin_so', '-L$lib_dir', '-lc',
            '$in_dir/${name}_first.c', '$crtend_so',
            '$soflags', '-o', '$out_dir/lib${name}_first.so'],
           ['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '-rdynamic', '-L$out_dir',
            '-Wl,--rpath-link=$out_dir', '-l${name}_first',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$$in', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'so_structors_test',
          ['$in_dir/$name.c', '$in_dir/structors_test.c'],
          '$out',
          [['$cc', '$cflags', '-DFOR_SHARED_OBJECT',
            '$ldflags', '-nostdlib',
            '$crtbegin_so', '-L$lib_dir', '-lc',
            '$in_dir/structors_test.c', '$crtend_so',
            '$soflags', '-o', '$out_dir/libstructors_test.so'],
           ['$cc', '$cflags', '$ldflags', '$execflags',
            '-nostdlib', '-rdynamic',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$in_dir/$name.c',
            '-L$out_dir', '-Wl,--rpath-link=$out_dir', '-lstructors_test',
            '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'dlopen_structors_test', ['$in_dir/$name.c'], '$out',
          [['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['$$in', '-ldl', '$crtend_exe', '-o', '$$out']]),
      BionicFundamentalTest(
          'dlopen_error_test',
          ['$in_dir/$name.c',
           '$in_dir/use_undefined_sym.c', '$in_dir/use_use_undefined_sym.c'],
          '$out',
          [['$cc', '$cflags', '$ldflags', '-nostdlib',
            '$crtbegin_so', '-L$lib_dir', '-lc',
            '$in_dir/use_undefined_sym.c', '$crtend_so',
            '$soflags', '-o', '$out_dir/libuse_undefined_sym.so'],
           ['$cc', '$cflags', '$ldflags', '-nostdlib',
            '-L$out_dir', '-luse_undefined_sym',
            '$crtbegin_so', '-L$lib_dir', '-lc',
            '$in_dir/use_use_undefined_sym.c', '$crtend_so',
            '$soflags', '-o', '$out_dir/libuse_use_undefined_sym.so'],
           ['$cc', '$cflags', '$ldflags', '$execflags', '-nostdlib',
            '-rdynamic', '-L$out_dir',
            '$crtbegin_exe', '-L$lib_dir', '-lc'] +
           ninja_generator.get_libgcc_for_bionic() +
           ['-ldl', '$in_dir/$name.c', '$crtend_exe', '-o', '$$out']]),
  ])
  for test in bionic_tests:
    test.emit(n)

  rule_name = 'run_bionic_fundamental_tests'
  script_name = os.path.join(BionicFundamentalTest._get_src_dir(),
                             'run_bionic_fundamental_tests.py')
  n.rule(rule_name,
         command=script_name +
         build_common.get_test_output_handler(use_crash_analyzer=True),
         description=rule_name + ' $in')
  result = os.path.join(BionicFundamentalTest._get_out_dir(),
                        rule_name + '.result')
  test_deps = BionicFundamentalTest.ALL_OUTPUT_BINARIES + [script_name]
  if OPTIONS.is_bare_metal_build():
    test_deps.append(build_common.get_bare_metal_loader())
  n.build(result, rule_name, implicit=test_deps)


def _generate_crt_bionic_ninja():
  n = ninja_generator.CNinjaGenerator('bionic_crt')
  _add_bare_metal_flags_to_ninja_generator(n)
  # Needed to access private/__dso_handle.h from crtbegin_so.c.
  n.add_include_paths('android/bionic/libc')
  rule_name = 'build_bionic_crt'
  n.rule(rule_name,
         deps='gcc',
         depfile='$out.d',
         command=(toolchain.get_tool(OPTIONS.target(), 'cc') +
                  ' $cflags -W -Werror '
                  ' -I' + staging.as_staging('android/bionic/libc/private') +
                  ' -fPIC -g -O -MD -MF $out.d -c $in -o'
                  ' $out'),
         description=rule_name + ' $in')
  # crts is a list of tuples whose first element is the source code
  # and the second element is the name of the output object.
  if OPTIONS.is_arm():
    crts = [
        ('android/bionic/libc/arch-arm/bionic/crtbegin.c', 'crtbegin.o'),
        ('android/bionic/libc/arch-arm/bionic/crtbegin_so.c', 'crtbeginS.o'),
        ('android/bionic/libc/arch-arm/bionic/crtend.S', 'crtend.o'),
        ('android/bionic/libc/arch-arm/bionic/crtend_so.S', 'crtendS.o'),
    ]
  else:
    # We use arch-nacl directory for x86 mainly because we use GCC
    # 4.4.3 for x86 NaCl. Recent GCC (>=4.7) uses .init_array and
    # .fini_array instead of .ctors and .dtors and the upstream code
    # expects we use recent GCC. We can use crtend.c for both crtend.o
    # and crtendS.o. Unlike ARM, we do not have .preinit_array,
    # which is not allowed in shared objects.
    crts = [
        ('android/bionic/libc/arch-nacl/bionic/crtbegin.c', 'crtbegin.o'),
        ('android/bionic/libc/arch-nacl/bionic/crtbegin_so.c', 'crtbeginS.o'),
        ('android/bionic/libc/arch-nacl/bionic/crtend.c', 'crtend.o'),
        ('android/bionic/libc/arch-nacl/bionic/crtend.c', 'crtendS.o'),
    ]
  for crt_src, crt_o in crts:
    source = staging.as_staging(crt_src)
    n.build(os.path.join(build_common.get_load_library_path(), crt_o),
            rule_name, source)


def _generate_linker_script_for_runnable_ld():
  # For Bare Metal mode, we do not modify linker script.
  if OPTIONS.is_bare_metal_build():
    return []

  rule_name = 'gen_runnable_ld_lds'
  n = ninja_generator.NinjaGenerator(rule_name)
  cc = toolchain.get_tool(OPTIONS.target(), 'cc')
  n.rule(rule_name,
         command='$in %s > $out || (rm $out; exit 1)' % cc,
         description=rule_name)
  linker_script = os.path.join(build_common.get_build_dir(), 'runnable-ld.lds')
  n.build(linker_script, rule_name, staging.as_staging(
      'android/bionic/linker/arch/nacl/gen_runnable_ld_lds.py'))
  return linker_script


def _add_runnable_ld_cflags(n):
  n.add_c_flags('-std=gnu99')
  if OPTIONS.is_arm():
    # If we specify -fstack-protector, the ARM compiler emits code
    # which requires relocation even for the code to be executed
    # before the self relocation. We disable the stack smashing
    # protector for the Bionic loader for now.
    # TODO(crbug.com/342292): Enable stack protector for the Bionic
    # loader on Bare Metal ARM.
    n.add_compiler_flags('-fno-stack-protector')
  n.add_compiler_flags(
      '-ffunction-sections', '-fdata-sections',
      # The loader does not need to export any symbols.
      '-fvisibility=hidden',
      '-W', '-Wno-unused', '-Wno-unused-parameter', '-Werror')

  # TODO(crbug.com/243244): Consider using -Wsystem-headers.
  n.add_include_paths('android/bionic/libc',
                      'android/bionic/libc/private',
                      'android/bionic/linker/arch/nacl')
  if OPTIONS.is_debug_code_enabled() or OPTIONS.is_bionic_loader_logging():
    n.add_defines('LINKER_DEBUG=1')
  else:
    n.add_defines('LINKER_DEBUG=0')
  n.add_defines('ANDROID_SMP=1')
  if OPTIONS.is_arm():
    n.add_defines('ANDROID_ARM_LINKER')
  elif OPTIONS.is_x86_64():
    n.add_defines('ANDROID_X86_64_LINKER')
    n.add_c_flags('-Wno-pointer-to-int-cast')
    n.add_c_flags('-Wno-int-to-pointer-cast')
  else:
    n.add_defines('ANDROID_X86_LINKER')
  if build_common.use_ndk_direct_execution():
    n.add_defines('USE_NDK_DIRECT_EXECUTION')

  if OPTIONS.is_bionic_loader_logging():
    n.add_defines('BIONIC_LOADER_LOGGING')
  _add_bare_metal_flags_to_ninja_generator(n)


def _generate_runnable_ld_ninja():
  linker_script = _generate_linker_script_for_runnable_ld()

  # Not surprisingly, bionic's loader is built with a special hack to
  # Android's build system so we cannot use MakefileNinjaTranslator.
  n = ninja_generator.ExecNinjaGenerator('runnable-ld.so',
                                         base_path='android/bionic/linker',
                                         install_path='/lib',
                                         is_system_library=True)
  _add_runnable_ld_cflags(n)

  n.add_library_deps('libc_bionic_linker.a')  # logging functions
  n.add_library_deps('libc_common_linker.a')
  n.add_library_deps('libc_freebsd_linker.a')  # __swsetup etc.
  sources = n.find_all_sources()
  sources.extend(['android/bionic/libc/arch-nacl/syscalls/irt_syscalls.c',
                  'android/bionic/libc/bionic/__errno.c',
                  'android/bionic/libc/bionic/pthread.c',
                  'android/bionic/libc/bionic/pthread_create.cpp',
                  'android/bionic/libc/bionic/pthread_internals.cpp',
                  'android/bionic/libc/bionic/pthread_key.cpp'])
  if OPTIONS.is_bare_metal_build():
    # Remove SFI NaCl specific dynamic code allocation.
    sources.remove('android/bionic/linker/arch/nacl/nacl_dyncode_alloc.c')
    sources.remove('android/bionic/linker/arch/nacl/nacl_dyncode_map.c')
  _remove_assembly_source(sources)
  # NaCl has no signals so debugger support cannot be implemented.
  sources.remove('android/bionic/linker/debugger.cpp')

  # n.find_all_sources() picks up this upstream file regardless of the
  # current target. For ARM, the file is obviously irrelevant. For i686
  # and x86_64, we use our own begin.c.
  sources.remove('android/bionic/linker/arch/x86/begin.c')

  ldflags = n.get_ldflags()
  if OPTIONS.is_nacl_build():
    ldflags += (' -T ' + linker_script +
                ' -Wl,-Ttext,' + _LOADER_TEXT_SECTION_START_ADDRESS)
  else:
    # We need to use recent linkers for __ehdr_start.
    ldflags += ' -pie'
  # See the comment in linker/arch/nacl/begin.c.
  ldflags += ' -Wl,--defsym=__linker_base=0'
  # --gc-sections triggers an assertion failure in GNU ld for ARM for
  # --opt build. The error message is very similar to the message in
  # https://sourceware.org/bugzilla/show_bug.cgi?id=13990
  # Once NaCl team updates the version of their binutils, we might be
  # able to remove this.
  if not OPTIONS.is_arm():
    ldflags += ' -Wl,--gc-sections'
  if not OPTIONS.is_debug_info_enabled():
    ldflags += ' -Wl,--strip-all'
  n.add_library_deps(*ninja_generator.get_libgcc_for_bionic())
  n.add_library_deps('libbionic_ssp.a')
  n.build_default(sources, base_path=None)
  n.link(variables={'ldflags': ldflags}, implicit=linker_script)


def _generate_bionic_tests():
  n = ninja_generator.TestNinjaGenerator('bionic_test',
                                         base_path='android/bionic/tests')
  _add_bare_metal_flags_to_ninja_generator(n)

  def relevant(f):
    if f.find('/fundamental/') >= 0:
      return False
    if re.search(r'(_benchmark|/benchmark_main)\.cpp$', f):
      return False
    if OPTIONS.enable_valgrind():
      # A few tests in these files fail under valgrind probably due to
      # a valgrind's bug around rounding mode. As it is not important
      # to run these tests under valgrind, we simply do not build them.
      if f in ['android/bionic/tests/fenv_test.cpp',
               'android/bionic/tests/math_test.cpp']:
        return False
    excludes = [
        # We do not support eventfd.
        'android/bionic/tests/eventfd_test.cpp',
        # We do not compile this as this test does not pass the NaCl
        # validation.
        # TODO(crbug.com/342292): Enable stack protector on BMM.
        'android/bionic/tests/stack_protector_test.cpp',
        # We do not support death tests.
        'android/bionic/tests/stack_unwinding_test.cpp',
        # Neither NaCl nor Bare Metal supports statvfs and fstatvfs.
        'android/bionic/tests/statvfs_test.cpp',
    ]
    return f not in excludes

  sources = filter(relevant, n.find_all_sources(include_tests=True))
  n.build_default(sources, base_path=None)
  # Set the same flag as third_party/android/bionic/tests/Android.mk.
  # This is necessary for dlfcn_test.cpp as it calls dlsym for this symbol.
  ldflags = '$ldflags -Wl,--export-dynamic -Wl,-u,DlSymTestFunction'
  if OPTIONS.is_arm():
    # Disables several pthread tests because pthread is flaky on qemu-arm.
    disabled_tests = ['pthread.pthread_attr_setguardsize',
                      'pthread.pthread_attr_setstacksize',
                      'pthread.pthread_create',
                      'pthread.pthread_getcpuclockid__no_such_thread',
                      'pthread.pthread_join__multijoin',
                      'pthread.pthread_join__no_such_thread',
                      'pthread.pthread_no_join_after_detach',
                      'pthread.pthread_no_op_detach_after_join',
                      'string.strsignal_concurrent',
                      'string.strerror_concurrent']
    n.add_qemu_disabled_tests(*disabled_tests)
  n.add_compiler_flags('-W', '-Wno-unused-parameter', '-Werror')
  # GCC's builtin ones should be disabled when testing our own ones.
  # TODO(crbug.com/357564): Change this to -fno-builtin.
  for f in ['bzero', 'memcmp', 'memset', 'nearbyint', 'nearbyintf',
            'nearbyintl', 'sqrt', 'strcmp', 'strcpy', 'strlen']:
    n.add_compiler_flags('-fno-builtin-' + f)
  n.run(n.link(variables={'ldflags': ldflags}))


def _generate_libgcc_ninja():
  # Currently, we need to generate libgcc.a only for Bare Metal mode.
  if not OPTIONS.is_bare_metal_build():
    return

  # TODO(crbug.com/283798): Build libgcc by ourselves.
  rule_name = 'generate_libgcc'
  n = ninja_generator.NinjaGenerator(rule_name)
  if OPTIONS.is_i686():
    # We use libgcc.a in Android NDK for Bare Metal mode as it is
    # compatible with Bionic.
    orig_libgcc = ('third_party/ndk/toolchains/x86-4.6/prebuilt/'
                   'linux-x86/lib/gcc/i686-linux-android/4.6/libgcc.a')
    # This libgcc has unnecessary symbols such as __CTORS__ in
    # _ctors.o. We define this symbol in crtbegin.o, so we need to
    # remove this object from the archive.
    # Functions in generic-morestack{,-thread}.o and morestack.o are not
    # needed if one is not using split stacks and it interferes with our
    # process emulation code.
    remove_object = ('_ctors.o generic-morestack.o generic-morestack-thread.o '
                     'morestack.o')
  elif OPTIONS.is_arm():
    # NDK's libgcc.a is not compatible with Bare Metal mode because
    # Android NDK does not use -mfloat-abi=hard. We just use libgcc
    # from Goobuntu.
    # TODO(crbug.com/340598): Check if we can use NDK's libgcc.a if we
    # decide to use softfp.
    orig_libgcc = os.path.join(
        ninja_generator.get_libgcc_installed_dir_for_bare_metal(), 'libgcc.a')
    # This object depends on some glibc specific symbols around
    # stdio. As no objects in libgcc.a use _eprintf, we can simply
    # remove this object.
    remove_object = '_eprintf.o'
  n.rule(rule_name,
         command=('cp $in $out.tmp && ar d $out.tmp %s && mv $out.tmp $out' %
                  remove_object),
         description=rule_name + ' $out')
  n.build(ninja_generator.get_libgcc_for_bare_metal(), rule_name, orig_libgcc)


def _generate_libstdcpp_ninja():
  def _filter(vars):
    if vars.is_static():
      return False
    Filters.convert_to_notices_only(vars)
    vars.set_canned(True)
    return True

  MakefileNinjaTranslator('android/bionic/libstdc++').generate(_filter)


def generate_ninjas():
  ninja_generator_runner.request_run_in_parallel(
      _generate_naclized_i686_asm_ninja,
      _generate_libc_ninja,
      _generate_libm_ninja,
      _generate_libdl_ninja,
      _generate_libstdcpp_ninja,
      _generate_runnable_ld_ninja,
      _generate_crt_bionic_ninja,
      _generate_libgcc_ninja)


def generate_test_ninjas():
  ninja_generator_runner.request_run_in_parallel(
      _generate_bionic_fundamental_tests,
      _generate_bionic_tests)
