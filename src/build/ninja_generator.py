# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# TODO(crbug.com/312571): The class name suffix XxxNinjaGenerator looks
# redundant. Rename NinjaGenerator family into simpler one.

import collections
import copy
import fnmatch
import hashlib
import json
import logging
import re
import os
import StringIO
import sys

import analyze_diffs
import build_common
import open_source
import pipes
import staging
import toolchain
import wrapped_functions
from build_common import as_list, as_dict
from build_common import find_all_files
from build_options import OPTIONS
from ninja_generator_runner import request_run_in_parallel
from notices import Notices

# Pull in ninja_syntax from our tools/ninja directory.
sys.path.insert(0, 'third_party/tools/ninja/misc')
import ninja_syntax

# Extensions of primary source files.
_PRIMARY_EXTENSIONS = ['.c', '.cpp', '.cc', '.java', '.S', '.s']


def get_libgcc_for_bare_metal():
  return os.path.join(build_common.get_build_dir(),
                      'intermediates/libgcc/libgcc.a')


def get_libgcc_installed_dir_for_bare_metal():
  assert OPTIONS.is_bare_metal_build()
  return ('third_party/ndk/toolchains/arm-linux-androideabi-4.6/prebuilt/'
          'linux-x86/lib/gcc/arm-linux-androideabi/4.6/armv7-a')


def _get_libgcc_for_bionic_realpath():
  # TODO(crbug.com/283798): We might need to build libgcc by ourselves.
  if OPTIONS.is_nacl_build():
    # GCC emits code to call functions in libgcc when the instruction
    # sequence will be too long if it emits inline code.
    # http://gcc.gnu.org/onlinedocs/gccint/Libgcc.html
    #
    # We use newlib's libgcc.a because glibc's libgcc.a defines all
    # symbols with __attribute__((visibility("hidden"))) so we cannot
    # expose these symbols from libc.so. We cannot also use libgcc.so for
    # glibc as it has a DT_NEEDED entry to glibc's libc.so.
    if OPTIONS.is_arm():
      return [os.path.join(
          toolchain.get_nacl_sdk_path(),
          'toolchain/linux_arm_newlib/lib/gcc/arm-nacl/4.8.3/libgcc.a')]
    else:
      bits_subdir = '' if OPTIONS.is_x86_64() else '32/'
      return [os.path.join(
          toolchain.get_nacl_sdk_path(),
          'toolchain/linux_x86_newlib/lib/gcc/x86_64-nacl/4.4.3/%slibgcc.a' %
          bits_subdir)]
  elif OPTIONS.is_bare_metal_build():
    if OPTIONS.is_i686():
      return [get_libgcc_for_bare_metal()]
    elif OPTIONS.is_arm():
      libgcc = [get_libgcc_for_bare_metal()]
      return libgcc
  raise Exception('Bionic is not supported yet for ' + OPTIONS.target())


def get_libgcc_for_bionic():
  """Returns libgcc path for the current target.

  When libgcc for the current target exists under third party directory, this
  function returns the corresponding staging path, which starts with
  out/staging.
  """
  return map(staging.third_party_to_staging, _get_libgcc_for_bionic_realpath())


class _TargetGroupInfo(object):
  def __init__(self):
    self.outputs = set()
    self.inputs = set()
    self.required_target_groups = set()

  def get_root_set(self):
    return self.outputs - self.inputs


class _TargetGroups(object):
  # We are trying to keep the number of target groups to a small,
  # managable level, so we whitelist the ones that are allowed.
  ALL = 'all'
  DEFAULT = 'default'

  def __init__(self):
    self._map = collections.defaultdict(_TargetGroupInfo)
    self._started_emitting = False
    self._allowed = set()
    self.define_target_group(self.ALL)
    self.define_target_group(self.DEFAULT)

  def define_target_group(self, target_group, required=None):
    assert set(as_list(required)) <= self._allowed
    self._allowed.add(target_group)
    self._map[target_group].required_target_groups = as_list(required)

  def record_build_rule(self, target_groups, outputs, inputs):
    """Remembers the build rule for later writing target group rule."""
    if self._started_emitting:
      return
    if not target_groups <= self._allowed:
      raise Exception('Unexpected target groups: %s' %
                      (target_groups - self._allowed))
    for target_group in target_groups:
      my_info = self._map[target_group]
      my_info.outputs |= outputs
      my_info.inputs |= inputs

  def emit_rules(self, n):
    self._started_emitting = True
    for tg, tgi in self._map.iteritems():
      implicit = (sorted(list(tgi.required_target_groups)) +
                  sorted(list(tgi.get_root_set())))
      n.build(tg, 'phony', implicit=implicit)
    n.default(self.DEFAULT)


class _VariableValueBuilder(object):
  """Utility class for extending an existing Ninja variable (defined in an
  different scope) with additional flags"""

  def __init__(self, base_flag):
    super(_VariableValueBuilder, self).__init__()
    self._base_flag = base_flag
    self._extra = []

  def append_flag(self, flag):
    """Adds the indicated flag"""
    self._extra.append(flag)

  def append_flag_pattern(self, flag_pattern, values):
    """Formats the given flag pattern using each entry in values."""
    for value in as_list(values):
      self._extra.append(flag_pattern % value)

  def append_optional_path_list(self, flag, paths):
    """If paths is not empty, adds a flag for the paths."""
    if paths:
      self.append_flag(flag + ' ' + ':'.join(paths))

  def __str__(self):
    extra = ' '.join(self._extra)
    if self._base_flag:
      return '$%s %s' % (self._base_flag, extra)
    else:
      return extra


class _BootclasspathComputer(object):

  _string = None
  _classes = []
  _installed_jars = []

  @staticmethod
  def _compute():
    """Compute the system's bootclasspath.

    The odex format and dependency analysis requires the bootclasspath
    contents and order to be the same during build time and run time.
    This function determines that bootclasspath.
    """
    if _BootclasspathComputer._string is None:
      upstream = _extract_pattern_from_file(
          'third_party/android/build/target/product/core_base.mk',
          'PRODUCT_BOOT_JARS := (.*)')
      upstream_installed = ['/system/framework/%s.jar' % n
                            for n in upstream.split(':')]
      # We do not have mms-common.jar yet.
      upstream_installed.remove('/system/framework/mms-common.jar')
      # Insert arc-services-framework.jar before services.jar which depends
      # on it.
      upstream_installed.insert(
          upstream_installed.index('/system/framework/services.jar'),
          '/system/framework/arc-services-framework.jar')
      # Insert cmds.jar before arc-services-fromework.jar which depends on it.
      upstream_installed.insert(
          upstream_installed.index(
              '/system/framework/arc-services-framework.jar'),
          '/system/framework/cmds.jar')
      _BootclasspathComputer._string = ':'.join(upstream_installed)
      _BootclasspathComputer._installed_jars = upstream_installed
      _BootclasspathComputer._classes = [
          build_common.get_build_path_for_jar(
              os.path.splitext(os.path.basename(j))[0],
              subpath='classes.jar')
          for j in upstream_installed]

  @staticmethod
  def get_string():
    """Return string representation of runtime bootclasspath.

    This is something like /system/framework/core.jar:...."""
    _BootclasspathComputer._compute()
    return _BootclasspathComputer._string

  @staticmethod
  def get_installed_jars():
    """Returns array of installed bootclasspath jars."""
    _BootclasspathComputer._compute()
    return _BootclasspathComputer._installed_jars

  @staticmethod
  def get_classes():
    """Returns array of bootclasspath classes.jar files."""
    _BootclasspathComputer._compute()
    return _BootclasspathComputer._classes


class NinjaGenerator(ninja_syntax.Writer):
  """Encapsulate ninja file generation.

  Simplify ninja file generation by naming, creating, and tracking
  all ninja files.  This removes boilerplate code required to
  create new ninja files.
  """

  # Global list of all ninjas generated in this parallel task.
  _ninja_list = []

  # Default implicit dependencies.
  _default_implicit = []

  def __init__(self, module_name, ninja_name=None,
               host=False, generate_path=True, base_path=None,
               implicit=None, target_groups=None,
               extra_notices=None, notices_only=False):
    if ninja_name is None:
      ninja_name = module_name
    self._module_name = module_name
    self._ninja_name = ninja_name
    self._is_host = host
    if generate_path:
      ninja_path = NinjaGenerator._get_generated_ninja_path(ninja_name,
                                                            self._is_host)
    else:
      ninja_path = ninja_name
    super(NinjaGenerator, self).__init__(StringIO.StringIO())
    NinjaGenerator._ninja_list.append(self)
    self._ninja_path = ninja_path
    self._base_path = base_path
    self._notices_only = notices_only
    self._implicit = as_list(implicit) + NinjaGenerator._default_implicit
    self._target_groups = NinjaGenerator._canonicalize_set(target_groups)
    self._build_rule_list = []
    self._root_dir_install_targets = []
    self._build_dir_install_targets = []
    self._notices = Notices()
    if extra_notices:
      if OPTIONS.is_notices_logging():
        print 'Adding extra notices to %s: %s' % (module_name, extra_notices)
      self._notices.add_sources(extra_notices)
    # TODO(crbug.com/366751): remove notice_archive hack when possible
    self._notice_archive = None

  @staticmethod
  def emit_common_rules(n):
    n.rule('copy_symbols_file',
           'src/build/symbol_tool.py --clean $in > $out',
           description='copy_symbols_file $in $out')
    n.rule('cp',
           'cp $in $out',
           description='cp $in $out')
    n.rule('dump_defined_symbols',
           'src/build/symbol_tool.py --dump-defined $in > $out',
           description='dump_defined_symbols $in')
    n.rule('dump_undefined_symbols',
           'src/build/symbol_tool.py --dump-undefined $in > $out',
           description='dump_undefined_symbols $in')
    n.rule('install',
           'rm -f $out; cp $in $out',
           description='install $out')
    n.rule('mkdir_empty',
           'mkdir -p $out && touch $out',
           description='make empty $out')
    # TODO(crbug.com/242783): Would be nice we can make directories readonly.
    n.rule('readonly_install',
           'rm -f $out; cp $in $out; chmod -w $out',
           description='install $out as readonly')
    n.rule('touch',
           'touch $out')
    n.rule('verify_disallowed_symbols',
           ('src/build/symbol_tool.py --verify $in $disallowed_symbols && '
            'touch $out'),
           description='verify_disallowed_symbols $out')
    # $command must create $out on success.
    n.rule('run_shell_command',
           command='$command || (rm $out; exit 1)',
           description='execute $command')

    # Rule to make the list of external symbols in a shared library.
    # Setting restat to True so that ninja can stop building its dependents
    # when the content is not modified.
    n.rule('mktoc',
           'src/build/make_table_of_contents.py %s $in $out' % OPTIONS.target(),
           description='make_table_of_contents $in',
           restat=True)

  @staticmethod
  def consume_ninjas():
    """Returns the list of NinjaGenerator created in the process."""
    # Note: this method should never be called by any modules except
    # ninja_generator_runner.
    result = NinjaGenerator._ninja_list
    NinjaGenerator._ninja_list = []
    return result

  @staticmethod
  def _canonicalize_set(target_groups):
    canon = set(as_list(target_groups))
    canon.add(_TargetGroups.ALL)
    if len(canon) == 1:
      canon.add(_TargetGroups.DEFAULT)
    return canon

  def emit(self):
    """Emits the contents of ninja script to the file."""
    with open(self._ninja_path, 'w') as f:
      f.write(self.output.getvalue())

  def add_flags(self, key, *values):
    values = [pipes.quote(x) for x in values]
    self.variable(key, '$%s %s' % (key, ' '.join(values)))
    return self

  def is_host(self):
    return self._is_host

  def get_module_name(self):
    return self._module_name

  def get_base_path(self):
    return self._base_path

  def get_build_path(self, name):
    return os.path.join(self.get_intermediates_dir(), name)

  @staticmethod
  def _add_bionic_stdlibs(flags, is_so, is_system_library):
    # We link crt(begin|end)(_so).o into everything except runnable-ld.so.
    if is_so:
      flags.insert(0, '$crtbegin_for_so')
      flags.append(build_common.get_bionic_crtend_so_o())
    elif not is_system_library:
      flags.insert(0, build_common.get_bionic_crtbegin_o())
      flags.append(build_common.get_bionic_crtend_o())

  @staticmethod
  def _add_target_library_flags(target, flags,
                                is_so=False, is_system_library=False):
    if OPTIONS.is_bare_metal_build() or target == 'host':
      # We intentionally do not set --thread flag of gold. This
      # feature seems to be flaky for us. See crbug.com/366358
      flags.extend(['-Bthird_party/gold', '-fuse-ld=gold'])
    if target == 'host':
      flags.extend(['-lpthread', '-ldl', '-lrt'])
    else:
      CNinjaGenerator._add_bionic_stdlibs(flags, is_so, is_system_library)

  def get_ldflags(self):
    return '$commonflags -Wl,-z,noexecstack -pthread%s -nostdlib' % (
        self._get_debug_ldflags())

  def _get_debug_ldflags(self):
    if OPTIONS.is_debug_info_enabled():
      return ''
    else:
      return ' -Wl,--strip-all'

  @staticmethod
  def _get_target_ld_flags(target, is_so=False, is_system_library=False):
    flags = []

    if is_so:
      flag_variable = '$hostldflags' if target == 'host' else '$ldflags'
      flags.extend(['-shared', flag_variable, '-Wl,-Bsymbolic', '@$out.files'])
    else:
      if (target != 'host' and OPTIONS.is_bare_metal_build() and
          not is_system_library):
        flags.append('-pie')
      flags.append('$in')

    flags.extend(['-Wl,--start-group,--whole-archive',
                  '$my_whole_archive_libs',
                  '-Wl,--end-group,--no-whole-archive',
                  '-Wl,--start-group',
                  '$my_static_libs',
                  '$my_shared_libs',
                  '-Wl,--end-group',
                  '$ldadd'])

    if target != 'host' and OPTIONS.is_bare_metal_build():
      # arm-nacl-gcc and gcc of Goobuntu use --hash-style=gnu by
      # default, but the bionic loader cannot handle gnu hash.
      flags.append('-Wl,--hash-style=sysv')
    # --build-id is expected by 'perf report' tool to more reliably identify
    # original binaries when it looks for symbol information.
    # Additionally this flag is needed to match up symbol uploads for
    # breakpad.
    flags.append('-Wl,--build-id')

    # This is needed so that symbols in the main executables can be
    # referenced in loaded shared libraries.
    flags.append('-rdynamic')

    # Force ET_EXEC to export _Unwind_GetIP for Bionic build. Because
    # libc_malloc_debug_leak.so has an undefined reference to this
    # symbol, it cannot be dlopen'ed if the main binary does not have
    # this symbol.
    # TODO(crbug.com/283798): We can remove this if we decide to
    # create libgcc.so instead of libgcc.a.
    # TODO(crbug.com/319020): Bare Metal ARM would require another symbol.
    if not is_so and not OPTIONS.is_arm():
      flags.append('-Wl,-u,_Unwind_GetIP')

    NinjaGenerator._add_target_library_flags(
        target, flags, is_so=is_so, is_system_library=is_system_library)

    # Make sure we have crtbegin as the first object and crtend as the
    # last object for Bionic build.
    if (target != 'host' and (is_so or not is_system_library)):
      assert re.search(r'/crtbegin.o|\$crtbegin_for_so', flags[0])
      assert re.search(r'/crtendS?\.o', flags[-1])

    return ' '.join(flags)

  @staticmethod
  def _rebase_to_build_dir(path):
    return os.path.join(build_common.get_build_dir(), path.lstrip(os.sep))

  def install_to_root_dir(self, output, inputs):
    top_dir = output.lstrip(os.path.sep).split(os.path.sep)[0]
    if top_dir not in ['dev', 'proc', 'sys', 'system', 'vendor']:
      raise Exception(output + ' does not start with known top dir')
    root_path = build_common.get_android_fs_path(output)
    self.build(root_path, 'readonly_install', inputs)
    self._root_dir_install_targets.append(output)

  def install_to_build_dir(self, output, inputs):
    out_path = self._rebase_to_build_dir(output)
    self.build(out_path, 'install', inputs)
    self._build_dir_install_targets.append('/system/' + output.lstrip(os.sep))

  def is_installed(self):
    return self._build_dir_install_targets or self._root_dir_install_targets

  @staticmethod
  def add_global_implicit_dependency(deps):
    NinjaGenerator._default_implicit.extend(deps)

  def find_all_files(self, base_paths, suffix, **kwargs):
    return find_all_files(base_paths,
                          suffixes=suffix,
                          **kwargs)

  def find_all_contained_files(self, suffix, **kwargs):
    return find_all_files([self._base_path], suffix, **kwargs)

  def _validate_outputs(self, rule, outputs):
    if rule == 'phony':
      # Builtin phony rule does not output any files.
      return
    for o in outputs:
      if (not o.startswith(build_common.OUT_DIR) and
          not o == 'build.ninja'):
        raise Exception('Output %s in invalid location' % o)
      if o.startswith(build_common.get_staging_root()):
        raise Exception('Output %s must not go to staging directory' % o)

  def add_notice_sources(self, sources):
    sources_including_tracking = sources[:]
    for s in sources:
      if (s.startswith(build_common.OUT_DIR) and
          not s.startswith(build_common.get_staging_root())):
        continue
      if not os.path.exists(s):
        continue
      with open_dependency(s, 'r', ignore_dependency=True) as f:
        tracking_file = analyze_diffs.compute_tracking_path(None, s, f)
        if tracking_file:
          sources_including_tracking.append(tracking_file)
    if OPTIONS.is_notices_logging():
      print 'Adding notice sources to %s: %s' % (self.get_module_name(),
                                                 sources_including_tracking)
    self._notices.add_sources(sources_including_tracking)

  def build(self, outputs, rule, inputs=None, variables=None,
            implicit=None, order_only=None, use_staging=True, **kwargs):
    outputs = as_list(outputs)
    all_inputs = as_list(inputs)
    in_real_path = []
    updated_inputs = []
    self._validate_outputs(rule, outputs)
    for i in all_inputs:
      if use_staging and staging.is_in_staging(i):
        in_real_path.append(staging.as_real_path(i))
        updated_inputs.append(staging.as_staging(i))
      else:
        in_real_path.append(i)
        updated_inputs.append(i)
    self.add_notice_sources(updated_inputs)
    if variables is None:
      variables = {}
    implicit = self._implicit + as_list(implicit)
    # Give a in_real_path for displaying to the user.  Realistically
    # if there are more than 5 inputs they'll be truncated when displayed
    # so truncate them now to save space in ninja files.
    variables['in_real_path'] = ' '.join(in_real_path[:5])

    self._build_rule_list.append((self._target_groups, set(outputs),
                                  set(as_list(implicit)) | set(all_inputs)))

    self._check_implicit(rule, implicit)
    self._check_order_only(implicit, order_only)
    return super(NinjaGenerator, self).build(outputs,
                                             rule,
                                             implicit=implicit,
                                             order_only=order_only,
                                             inputs=updated_inputs,
                                             variables=variables,
                                             **kwargs)

  @staticmethod
  def _get_generated_ninja_path(ninja_base, is_host):
    basename = ninja_base + ('_host.ninja' if is_host else '.ninja')
    return os.path.join(
        build_common.get_generated_ninja_dir(), basename)

  @staticmethod
  def _get_name_and_driver(rule_prefix, target):
    return (rule_prefix + '.' + target,
            toolchain.get_tool(target, rule_prefix))

  def emit_compiler_rule(self, rule_prefix, target, flag_name,
                         supports_deps=True, extra_flags=None):
    extra_flags = build_common.as_list(extra_flags)
    rule_name, driver_name = NinjaGenerator._get_name_and_driver(rule_prefix,
                                                                 target)
    if flag_name is None:
      flag_name = rule_prefix + 'flags'
    # We unfortunately need to avoid using -MMD due to the bug described
    # here: http://gcc.gnu.org/bugzilla/show_bug.cgi?id=28435 .
    # This means we will capture dependencies of changed system headers
    # (which is good since some of these we could be changing, and is
    # bad since some we will never change and it will slow down null
    # builds.)  The trade off is moot since we must have missing
    # headers result in errors.
    is_clang = rule_prefix.startswith('clang')
    if not is_clang and toolchain.get_gcc_version(target) >= [4, 8, 0]:
      # gcc 4.8 has a new check warning "-Wunused-local-typedefs", but most
      # sources are not ready for this.  So we disable this warning for now.
      extra_flags.append('-Wno-unused-local-typedefs')

    if supports_deps:
      self.rule(rule_name,
                deps='gcc',
                depfile='$out.d',
                command=(driver_name + ' -MD -MF $out.d $' + flag_name +
                         ' ' + ' '.join(extra_flags) + ' -c $in -o $out'),
                description=rule_name + ' $in_real_path')
    else:
      self.rule(rule_name,
                command=(driver_name + ' $' + flag_name +
                         ' ' + ' '.join(extra_flags) + ' -c $in -o $out'),
                description=rule_name + ' $in_real_path')

  def emit_linker_rule(self, rule_prefix, target, flag_name):
    rule_name, driver_name = NinjaGenerator._get_name_and_driver(rule_prefix,
                                                                 target)
    common_args = NinjaGenerator._get_target_ld_flags(
        target, is_so=False,
        is_system_library=('_system_library' in rule_prefix))
    self.rule(rule_name,
              command=(driver_name + ' $' + flag_name + ' -o $out ' +
                       common_args),
              description=rule_name + ' $out')

  def emit_ar_rule(self, rule_prefix, target):
    rule_name, driver_name = NinjaGenerator._get_name_and_driver(rule_prefix,
                                                                 target)
    self.rule(rule_name,
              command='rm -f $out && ' + driver_name + ' rcsT $out $in',
              description='archive $out')

  @staticmethod
  def get_symbols_path():
    return os.path.join(build_common.get_build_dir(), 'gen_symbols')

  def _check_order_only(self, implicit, order_only):
    """Checks if order_only dependency is used properly."""
    def _is_header(f):
      # .inc is a header file for .S or a generated header file by llvm-tblgen.
      # .gen is also a generated header file by llvm-tblgen.
      return os.path.splitext(f)[1] in ['.gen', '.h', '.inc']
    # Checking if |self| is CNinjaGenerator or its sub class is necessary
    # because for non-C/C++ generators, having header files in implicit is
    # sometimes valid. 'lint' rule is a good example.
    if isinstance(self, CNinjaGenerator) and implicit:
      implicit_headers = filter(lambda f: _is_header(f), implicit)
      if len(implicit_headers):
        raise Exception('C/C++/ASM headers should not be in implicit=. Use '
                        'order_only= instead: ' + str(implicit_headers))

    if order_only:
      non_headers = filter(lambda f: not _is_header(f), order_only)
      if len(non_headers):
        raise Exception('Only C/C++/ASM headers should be in order_only=. Use '
                        'implicit= instead: ' + str(non_headers))

  def _check_implicit(self, rule, implicit):
    """Checks that there are no implicit dependencies on third party paths.

    When a file in third party directory is inadvertently set as implicit,
    modifying the corresponding file in mods directory does not trigger
    rebuild. This check is for avoiding such incorrect implicit dependencies
    on files in third party directories.
    """
    # It is valid for lint rule to have implicit dependencies on third party
    # paths.
    if rule == 'lint':
      return
    # The list of paths for which implicit dependency check is skipped.
    implicit_check_skip_patterns = (
        # phony rule has implicit dependency on this.
        'build.ninja',
        # Files in canned directory are not staged and OK to be in implicit.
        'canned/*',
        # phony rule has implicit dependency on this.
        'default',
        # Files in mods are OK to be implicit because they are ensured to
        # trigger rebuild when they are modified unlike files in third party
        # directories.
        'internal/mods/*',
        'mods/*',
        # Files in out/ are generated files or in staging directory. It is
        # valid for them to be in implicit.
        'out/*',
        # Files in src are not overlaid by any files, so it is OK for the files
        # to be implicit.
        'src/*',
    )
    for dep in implicit:
      if os.path.isabs(dep):
        dep = os.path.relpath(dep, build_common.get_arc_root())
      if not any(fnmatch.fnmatch(dep, pattern) for pattern in
                 implicit_check_skip_patterns):
        raise Exception('%s in rule: %s\n'
                        'Avoid third_party/ paths in implicit dependencies; '
                        'use staging paths instead.' % (dep, rule))

  def _check_symbols(self, object_files, disallowed_symbol_files):
    for object_file in object_files:
      # Dump all undefined symbols in the |object_file|.
      undefined_symbol_file = os.path.join(
          self.get_symbols_path(), os.path.basename(object_file) + '.undefined')
      self.build([undefined_symbol_file], 'dump_undefined_symbols', object_file,
                 implicit='src/build/symbol_tool.py')
      for disallowed_symbol_file in disallowed_symbol_files:
        # Check the content of the |undefined_symbol_file|.
        disallowed_symbol_file_full = os.path.join(
            self.get_symbols_path(), disallowed_symbol_file)
        out_path = undefined_symbol_file + '.checked.' + disallowed_symbol_file
        self.build([out_path],
                   'verify_disallowed_symbols', undefined_symbol_file,
                   variables={'disallowed_symbols':
                              disallowed_symbol_file_full},
                   implicit=[disallowed_symbol_file_full,
                             'src/build/symbol_tool.py'])

  @staticmethod
  def get_installed_shared_libs(ninja_list):
    """Returns installed shared libs in the given ninja_list."""
    installed_shared_libs = []
    for ninja in ninja_list:
      if not isinstance(ninja, SharedObjectNinjaGenerator):
        continue
      for path in ninja.installed_shared_library_list:
        installed_shared_libs.append(build_common.get_build_dir() + path)
    return installed_shared_libs

  def get_notices_install_path(self):
    """Pick a name for describing this generated artifact in NOTICE.html."""
    if self._build_dir_install_targets:
      result = self._build_dir_install_targets[0]
    elif self._root_dir_install_targets:
      result = self._root_dir_install_targets[0]
    else:
      return None
    return result.lstrip(os.sep) + '.txt'

  # TODO(crbug.com/366751): remove notice_archive hack when possible
  def set_notice_archive(self, notice_archive):
    self._notice_archive = notice_archive

  def get_notice_archive(self):
    return self._notice_archive

  def get_included_module_names(self):
    """Return the list of NinjaGenerator module_names built into this module.

    This is necessary for licensing.  If a module is built into this module
    (with static linking, for instance), this module inherits the licenses of
    the included module."""
    return []


class CNinjaGenerator(NinjaGenerator):
  """Encapsulates ninja file generation for C and C++ files."""

  def __init__(self, module_name, ninja_name=None, enable_logtag_emission=True,
               gl_flags=False, enable_clang=False, **kwargs):
    super(CNinjaGenerator, self).__init__(module_name, ninja_name, **kwargs)
    # This is set here instead of TopLevelNinjaGenerator because the ldflags
    # depend on module name.
    self.variable('ldflags', self.get_ldflags())
    self._intermediates_dir = os.path.join(
        build_common.get_build_dir(is_host=self._is_host),
        'intermediates', self._ninja_name)
    if enable_logtag_emission:
      self.emit_logtag_flags()
    if not self._is_host:
      self.emit_globally_exported_include_dirs()
      if ('base_path' in kwargs and
          kwargs['base_path'].startswith('android/frameworks/')):
        self.emit_framework_common_flags()
        # android/frameworks/* is usually compiled with -w (disable warnings),
        # but for some white-listed paths, we can use -Werror.
        use_w_error = ['android/frameworks/base',
                       'android/frameworks/base/services/jni/arc',
                       'android/frameworks/native/arc/binder']
        if kwargs['base_path'] in use_w_error:
          self.add_compiler_flags('-Werror')
        else:
          # Show warnings when --show-warnings=all or yes is specified.
          self.add_compiler_flags(*OPTIONS.get_warning_suppression_cflags())
      if ('base_path' in kwargs and
          kwargs['base_path'].startswith('android/')):
        self.add_include_paths('android/bionic/libc/include')
    if gl_flags:
      self.emit_gl_common_flags()
    # We need 4-byte alignment to pass host function pointers to arm code.
    if not OPTIONS.is_nacl_build():
      self.add_compiler_flags('-falign-functions=4')
    self._enable_clang = (enable_clang and
                          toolchain.has_clang(OPTIONS.target(), self._is_host))
    self._object_list = []
    self._shared_deps = []
    self._static_deps = []
    self._whole_archive_deps = []

  def __del__(self):
    if OPTIONS.verbose():
      print 'Generated', self._ninja_name
    if self._object_list:
      print ('Warning: %s builds these objects but does nothing '
             'with them: %s' % (self._ninja_name, ' '.join(self._object_list)))

  def get_intermediates_dir(self):
    return self._intermediates_dir

  @staticmethod
  def add_to_variable(variables, flag_name, addend):
    if flag_name not in variables:
      variables[flag_name] = '$%s %s' % (flag_name, addend)
    else:
      variables[flag_name] += ' ' + addend

  def add_objects(self, object_list):
    self._object_list += object_list
    return self

  def _consume_objects(self):
    object_list = self._object_list
    self._object_list = []
    return object_list

  def build_default(self, files, base_path='', **kwargs):
    if base_path == '':
      base_path = self._base_path
    self.add_objects(build_default(
        self, base_path, files, **kwargs))
    return self

  def find_all_sources(self, **kwargs):
    return self.find_all_contained_files(_PRIMARY_EXTENSIONS, **kwargs)

  def build_default_all_sources(self, implicit=None, order_only=None,
                                exclude=None, **kwargs):
    all_sources = self.find_all_sources(exclude=exclude, **kwargs)
    return self.build_default(all_sources, implicit=implicit,
                              order_only=order_only, base_path=None, **kwargs)

  # prioritize_ctors causes us to change an object file, as if all of its
  # constructors had been declared with:
  # __attribute__((init_priority(<priority>))).
  def prioritize_ctors(self, input, priority):
    if priority < 101:
      # GNU ld docs say priorities less than 101 are reserved.
      print 'Illegal priority %d' % priority
      sys.exit(1)
    output = os.path.join(os.path.dirname(input),
                          '%s.prio%d.o' % (os.path.basename(input), priority))
    # Recent GNU gcc/ld put global constructor function pointers in
    # a section named .init_array.  If those constructors have
    # priorities associated with them the name of the section is
    # .init_array.<priority>.
    init_array_suffix = '.%05d' % priority
    # Old GNU gcc/ld use .ctors.<value> where value is that number
    # subtracted from 65535.
    ctors_suffix = '.%05d' % (65535 - priority)
    # Note that we do not need to modify .fini_array and .dtors for
    # C++ global destructors since they use atexit() instead of
    # special sections.
    return self.build(output, 'prioritize_ctors', input,
                      variables={'init_array_suffix': init_array_suffix,
                                 'ctors_suffix': ctors_suffix})

  def add_compiler_flags(self, *flags):
    flag_variable = 'hostcflags' if self._is_host else 'cflags'
    self.add_flags(flag_variable, *flags)
    self.add_asm_flag(*flags)
    self.add_cxx_flags(*flags)
    return self

  def add_asm_flag(self, *flags):
    flag_variable = 'hostasmflags' if self._is_host else 'asmflags'
    self.add_flags(flag_variable, *flags)
    return self

  # Same as add_compiler_flag but applies to C files only.
  def add_c_flags(self, *flags):
    flag_variable = 'hostcflags' if self._is_host else 'cflags'
    self.add_flags(flag_variable, *flags)
    return self

  # Same as add_compiler_flag but applies to C++ files only.
  def add_cxx_flags(self, *flags):
    flag_variable = 'hostcxxflags' if self._is_host else 'cxxflags'
    self.add_flags(flag_variable, *flags)
    return self

  def add_ld_flags(self, *flags):
    flag_variable = 'hostldflags' if self._is_host else 'ldflags'
    self.add_flags(flag_variable, *flags)
    return self

  # Passed library flags can be any style:
  #  -lerty
  #  path/to/liberty.so
  #  path/to/liberty.a
  def add_libraries(self, *flags):
    flag_variable = 'hostldadd' if self._is_host else 'ldadd'
    self.add_flags(flag_variable, *flags)

  # Avoid using -l since this can allow the linker to use a system
  # shared library instead of the library we have built.
  def _add_lib_vars(self, variables):
    joined_static_libs = ' '.join(self._static_deps)
    joined_whole_archive_libs = ' '.join(self._whole_archive_deps)
    joined_shared_libs = ' '.join(self._shared_deps)
    return dict({'my_static_libs': joined_static_libs,
                 'my_shared_libs': joined_shared_libs,
                 'my_whole_archive_libs': joined_whole_archive_libs}.items() +
                variables.items())

  def _add_library_deps(self, deps, as_whole_archive):
    for dep in deps:
      if dep.endswith('.so'):
        list = self._shared_deps
      elif dep.endswith('.a'):
        if as_whole_archive:
          list = self._whole_archive_deps
        else:
          list = self._static_deps
      else:
        raise Exception('Unexpected lib dependency: ' + dep)
      if os.path.sep not in dep:
        dep = build_common.get_build_path_for_library(
            dep, is_host=self._is_host)
      if dep not in list:
        list.append(dep)
    return self

  def add_library_deps(self, *deps):
    return self._add_library_deps(deps, False)

  def add_whole_archive_deps(self, *deps):
    return self._add_library_deps(deps, True)

  def add_include_paths(self, *paths):
    self.add_compiler_flags(*['-I' + staging.as_staging(x) for x in paths])
    return self

  def add_system_include_paths(self, *paths):
    """Adds -isystem includes. These should be avoided whenever possible
    due to warning masking that happens in code."""
    flags = []
    for path in paths:
      flags.extend(['-isystem', staging.as_staging(path)])
    self.add_compiler_flags(*flags)
    return self

  def add_defines(self, *defines):
    self.add_compiler_flags(*['-D' + x for x in defines])
    return self

  def get_object_path(self, src_path):
    """Generate a object path for the given source file.

    This path, relative to the intermediates directory for this ninja
    file, where the object files will be stored.  We need the same
    namespacing from the input directory structures, so we use the
    source container directory here in generating the path, but we
    just hash it to avoid having prohibitively long build paths.  We
    also carefully use the real path instead of the staging path.  The
    distinction is that we want the build path to change when a file
    flips from being overlaid to upstream and vice versa in order to
    prompt a rebuild.
    """
    real_src_container = os.path.dirname(staging.as_real_path(src_path))
    build_container = _compute_hash_fingerprint(real_src_container)
    path = os.path.join(build_container, os.path.basename(src_path))
    return os.path.splitext(path)[0] + '.o'

  @staticmethod
  def get_archasmflags():
    if OPTIONS.is_arm():
      archasmflags = (
          # Some external projects like libpixelflinger expect this macro.
          '-D__ARM_HAVE_NEON')
    else:
      archasmflags = ''

    archasmflags += ' -nostdinc -D__ANDROID__ '
    return archasmflags

  @staticmethod
  def _get_bionic_fpu_arch():
    if OPTIONS.is_i686():
      return 'i387'
    elif OPTIONS.is_x86_64():
      return 'amd64'
    elif OPTIONS.is_arm():
      return 'arm'
    assert False, 'Unsupported CPU architecture: ' + OPTIONS.target()

  @staticmethod
  def get_archcflags():
    archcflags = ''
    # If the build target uses linux x86 ABIs, stack needs to be aligned at
    # 16 byte boundary, although recent compiler outputs 16 byte aligned code.
    if OPTIONS.is_bare_metal_i686():
      # The flag comes from $ANDROID/build/core/combo/TARGET_linux-x86.mk. We
      # need this because the Android code has legacy assembly functions that
      # align the stack to a 4-byte boundary which is not compatible with SSE.
      # TODO(crbug.com/394688): The performance overhead should be
      # measured, and consider removing this flag.
      archcflags += ' -mstackrealign'

    if OPTIONS.is_bare_metal_build():
      archcflags += ' -fstack-protector'

    gcc_raw_version = toolchain.get_gcc_raw_version(OPTIONS.target())

    if OPTIONS.is_nacl_build():
      if OPTIONS.is_arm():
        compiler_include = os.path.join(
            toolchain.get_nacl_toolchain_root(),
            'lib/gcc/arm-nacl/%s/include' % gcc_raw_version)
      else:
        compiler_include = os.path.join(
            toolchain.get_nacl_toolchain_root(),
            'lib/gcc/x86_64-nacl/%s/include' % gcc_raw_version)
    else:
      if OPTIONS.is_arm():
        # Ubuntu 14.04 has this diriectory for cross-compile headers.
        if os.path.exists('/usr/lib/gcc-cross'):
          compiler_include = (
              '/usr/lib/gcc-cross/arm-linux-gnueabihf/%s/include' %
              gcc_raw_version)
        else:
          compiler_include = ('/usr/lib/gcc/arm-linux-gnueabihf/%s/include' %
                              gcc_raw_version)
      else:
        compiler_include = ('/usr/lib/gcc/x86_64-linux-gnu/%s/include' %
                            gcc_raw_version)
    archcflags += (
        # Pick compiler specific include paths (e.g., stdargs.h) first.
        ' -isystem ' + compiler_include +
        ' -isystem ' + '%s-fixed' % compiler_include +
        # TODO(crbug.com/243244): It might be probably a bad idea to
        # include files in libc/kernel from non libc code.
        # Check if they are really necessary once we can compile
        # everything with bionic.
        ' -isystem ' + staging.as_staging(
            'android/bionic/libc/kernel/common') +
        ' -isystem ' + staging.as_staging(
            'android/bionic/libc/kernel/%s' %
            build_common.get_bionic_arch_subdir_name()) +
        ' -isystem ' + staging.as_staging(
            'android/bionic/libc/%s/include' %
            build_common.get_bionic_arch_subdir_name()) +
        ' -isystem ' + staging.as_staging('android/bionic/libc/include') +
        ' -isystem ' + staging.as_staging('android/bionic/libm/include') +
        ' -isystem ' + staging.as_staging(
            'android/bionic/libc/arch-nacl/syscalls') +
        ' -isystem ' + staging.as_staging(
            'android/bionic/libm/include/%s' %
            CNinjaGenerator._get_bionic_fpu_arch()) +
        # Build gmock using the TR1 tuple library in gtest because tuple
        # implementation is not included in STLport.
        ' -DGTEST_HAS_TR1_TUPLE=1' +
        ' -DGTEST_USE_OWN_TR1_TUPLE=1')
    return archcflags

  @staticmethod
  def get_commonflags():
    archcommonflags = []
    if OPTIONS.is_arm():
      archcommonflags.extend([
          # Our target ARM device is either a15 or a15+a7 big.LITTLE. Note that
          # a7 is 100% ISA compatible with a15.
          # Unlike Android, we must use the hard-fp ABI since the ARM toolchains
          # for Chrome OS and NaCl does not support soft-fp.
          '-mcpu=cortex-a15',
          '-mfloat-abi=softfp'
      ])
      # The toolchains for building Android use -marm by default while the
      # toolchains for Bare Metal do not, so set -marm explicitly as the default
      # mode.
      if OPTIONS.is_bare_metal_build():
        archcommonflags.append('-marm')
    elif OPTIONS.is_i686():
      archcommonflags.append('-m32')

    archcommonflags.append(os.getenv('LDFLAGS', ''))
    # We always use -fPIC even for Bare Metal mode, where we create
    # PIE for executables. To determine whether -fPIC or -fPIE is
    # appropriate, we need to know if we are building objects for an
    # executable or a shared object. This is hard to tell especially
    # for ArchiveNinjaGenerator. Though -fPIC -pie is not supported
    # officially, it should be safe in practice. There are two
    # differences between -fPIC and -fPIE:
    # 1. GCC uses dynamic TLS model for -fPIC, while it uses static
    # TLS model for -fPIE. This is not an issue because we do not
    # support TLS based on __thread, and dynamic TLS model always
    # works even for code for which static TLS model is more
    # appropriate. See also: http://www.akkadia.org/drepper/tls.pdf.
    # 2. GCC uses PLT even for locally defined symbols if -fPIC is
    # specified. This makes no difference for us because the linker
    # will remove the call to PLT as we specify -Bsymbolic anyway.
    archcommonflags.append('-fPIC')
    return ' '.join(archcommonflags)

  @staticmethod
  def get_asmflags():
    return ('$commonflags ' +
            CNinjaGenerator.get_archasmflags() +
            '-pthread -Wall ' + CNinjaGenerator._get_debug_cflags() +
            '-DANDROID '
            # GCC sometimes predefines the _FORTIFY_SOURCE macro which is
            # not compatible with our function wrapping system. Undefine
            # the macro to turn off the feature. (crbug.com/226930)
            '-U_FORTIFY_SOURCE '
            '-DARC_TARGET=\\"' + OPTIONS.target() + '\\" ' +
            '-DARC_TARGET_PATH=\\"' + build_common.get_build_dir() +
            '\\" ' +
            '-DHAVE_ARC ')

  @staticmethod
  def get_cflags():
    cflags = ('$asmflags' +
              # These flags also come from TARGET_linux-x86.mk.
              # * -fno-short-enums is the default, but add it just in case.
              # * Although -Wstrict-aliasing is mostly no-op since we add
              #   -fno-strict-aliasing in the next line, we keep this since
              #   this might detect unsafe '-fstrict-aliasing' in the
              #   future when it is added by mistake.
              ' -fno-short-enums -Wformat-security -Wstrict-aliasing=2'
              # These flags come from $ANDROID/build/core/combo/select.mk.
              # ARC, Android, Chromium, and third_party libraries do not
              # throw exceptions at all.
              ' -fno-exceptions -fno-strict-aliasing'
              # Include dirs are parsed left-to-right. Prefer overriden
              # headers in our mods/ directory to those in third_party/.
              # Android keeps all platform-specific defines in
              # AndroidConfig.h.
              ' -include ' +
              build_common.get_android_config_header(is_host=False) +
              ' ' + CNinjaGenerator.get_archcflags())

    if OPTIONS.is_debug_info_enabled() or OPTIONS.is_debug_code_enabled():
      # We do not care the binary size when debug info or code is enabled.
      # Emit .eh_frame for better backtrace. Note that _Unwind_Backtrace,
      # which is used by libcorkscrew, depends on this.
      cflags += ' -funwind-tables'
    elif not OPTIONS.is_nacl_build():
      # Bare Metal build does not require the eh_frame section. Like Chromium,
      # remove the section to reduce the size of the text by 1-2%. Do not use
      # the options for NaCl because they do not reduce the size of the NaCl
      # binaries.
      cflags += ' -fno-unwind-tables -fno-asynchronous-unwind-tables'

    # Note: Do not add -fno-threadsafe-statics for now since we cannot be sure
    # that Android and third-party libraries we use do not depend on the C++11's
    # thread safe variable initialization feature (either intentionally or
    # accidentally) objdump reports that we have more than 2000 function-scope
    # static variables in total and that is too many to check. Neither select.mk
    # nor TARGET_linux-x86.mk has -fno-threadsafe-statics.

    cflags += (' -I' + staging.as_staging('src') +
               ' -I' + staging.as_staging('android_libcommon') +
               ' -I' + staging.as_staging('android') +
               # Allow gtest/gtest_prod.h to be included by anything.
               ' -I third_party/googletest/include')

    return cflags

  @staticmethod
  def get_cxxflags():
    # We specify '-nostdinc' as an archasmflags, but it does not remove C++
    # standard include paths for clang. '-nostdinc++' works to remove the paths
    # for both gcc and clang.
    cxx_flags = ' -nostdinc++'
    cxx_flags += (' -isystem ' + staging.as_staging(
        'android/external/stlport/stlport'))
    # This is necessary because STLport includes headers like
    # libstdc++/include/new.
    cxx_flags += (' -isystem ' + staging.as_staging('android/bionic'))
    if OPTIONS.enable_atrace():
      cxx_flags += ' -DARC_ANDROID_TRACE'
    if OPTIONS.enable_valgrind():
      # By default, STLport uses its custom allocator which does never
      # release the memory and valgrind thinks there is leaks. We tell
      # STLport to use new/delete instead of the custom allocator.
      # See http://stlport.sourceforge.net/FAQ.shtml#leaks
      cxx_flags += ' -D_STLP_USE_NEWALLOC'

    # ARC, Android, PPAPI libraries, and the third_party libraries (except
    # ICU) do not use RTTI at all. Note that only g++ supports the flags.
    # gcc does not.
    # C++ system include paths should be specified before C system
    # include paths.
    return cxx_flags + ' $cflags -fno-rtti'

  @staticmethod
  def get_hostcflags():
    # The host C flags are kept minimal as relevant flags, such as -Wall, are
    # provided from MakefileNinjaTranslator, and most of the host binaries
    # are built via MakefileNinjaTranslator.
    hostcflags = (' -I' + staging.as_staging('src') +
                  ' -I' + staging.as_staging('android_libcommon') +
                  ' -I' + staging.as_staging('android') +
                  # Allow gtest/gtest_prod.h to be included by anything.
                  ' -I third_party/googletest/include')
    return hostcflags

  @staticmethod
  def get_hostcxxflags():
    hostcxx_flags = ''
    # See the comment in get_cxxflags() about RTTI.
    return hostcxx_flags + ' $hostcflags -fno-rtti'

  @staticmethod
  def _get_gccflags():
    flags = []
    # In addition to -mstackrealign, we need to set
    # -mincoming-stack-boundary flag, that the incoming alignment is
    # at 4 byte boundary. Because it takes log_2(alignment bytes) so,
    # we set '2' which means 4 byte alignemnt.
    # Note this is needed only for GCC. Clang re-aligns the stack even
    # without this flag and it does not have this flag.
    # TODO(crbug.com/394688): The performance overhead should be
    # measured, and consider removing this flag.
    if OPTIONS.is_bare_metal_i686():
      flags.append('-mincoming-stack-boundary=2')
    if OPTIONS.is_arm():
      flags.extend(['-mthumb-interwork', '-mfpu=neon-vfpv4', '-Wno-psabi',
                    '-Wa,-mimplicit-it=thumb'])
    if OPTIONS.is_nacl_i686():
      # For historical reasons by default x86-32 NaCl produces code for quote
      # exotic CPU: 80386 with SSE instructions (but without SSE2!).
      # Let's use something more realistic.
      flags.extend(['-march=pentium4', '-mtune=core2'])
      # Use '-Wa,-mtune=core2' to teach assemler to use long Nops for padding.
      # This produces slightly faster code on all CPUs newer than Pentium4.
      flags.append('-Wa,-mtune=core2')
    if OPTIONS.is_nacl_x86_64():
      flags.append('-m64')
    return flags

  @staticmethod
  def _get_gxxflags():
    return []

  @staticmethod
  def _get_clangflags():
    flags = ['-Wheader-hygiene', '-Wstring-conversion']
    if OPTIONS.is_arm():
      flags.extend(['-target', 'arm-linux-gnueabi'])
    if OPTIONS.is_nacl_i686():
      flags.extend(['-target', 'i686-unknown-nacl', '-arch', 'x86-32',
                    '--pnacl-allow-translate'])
    if OPTIONS.is_nacl_x86_64():
      flags.extend(['-target', 'x86_64-unknown-nacl', '-arch', 'x86-64',
                    '--pnacl-allow-translate'])
    return flags

  @staticmethod
  def _get_clangxxflags():
    return ['-std=gnu++11', '-Wheader-hygiene', '-Wstring-conversion']

  @staticmethod
  def _get_debug_cflags():
    debug_flags = ''
    if not OPTIONS.is_debug_code_enabled():
      # Add NDEBUG to get rid of all *LOGV, *LOG_FATAL_IF, and *LOG_ASSERT calls
      # from our build.
      debug_flags += '-DNDEBUG '
    if OPTIONS.is_debug_info_enabled():
      debug_flags += '-g '
    return debug_flags

  @staticmethod
  def emit_optimization_flags(n, force_optimizations=False):
    cflags = []
    ldflags = []
    if OPTIONS.is_optimized_build() or force_optimizations:
      cflags = get_optimization_cflags()
      # Unlike Chromium where gold is available, do not use '-Wl,-O1' since it
      # slows down the linker a lot. Do not use '-Wl,--gc-sections' either
      # (crbug.com/231034).
      if OPTIONS.is_debug_code_enabled():
        # Even when forcing optimizations we keep the frame pointer for
        # debugging.
        # TODO(crbug.com/122623): Re-enable -fno-omit-frame-pointer for
        # nacl_x86_64 once the underlying compiler issue is fixed.
        # We are affected in experiencing odd gtest/gmock failures.
        #
        # TODO(crbug.com/378161): Re-enable -fno-omit-frame-pointer for
        # ARM GCC 4.8 once the underlying compiler issue is fixed.
        gcc_version = toolchain.get_gcc_version(OPTIONS.target())
        if not (OPTIONS.is_nacl_x86_64() or
                (OPTIONS.is_arm() and gcc_version >= [4, 8, 0])):
          cflags += ['-fno-omit-frame-pointer']
    else:
      cflags = ['-O0']

    n.variable('cflags', '$cflags ' + ' '.join(cflags))
    n.variable('cxxflags', '$cxxflags ' + ' '.join(cflags))
    n.variable('ldflags', '$ldflags ' + ' '.join(ldflags))

  @staticmethod
  def emit_target_rules_(n):
    target = OPTIONS.target()
    extra_flags = []
    if OPTIONS.is_nacl_build():
      extra_flags = ['$naclflags']
    n.emit_compiler_rule('cxx', target, flag_name='cxxflags',
                         extra_flags=extra_flags + ['$gxxflags'])
    n.emit_compiler_rule('cc', target, flag_name='cflags',
                         extra_flags=extra_flags + ['$gccflags'])
    if toolchain.has_clang(target):
      n.emit_compiler_rule('clangxx', target, flag_name='cxxflags',
                           extra_flags=extra_flags + ['$clangxxflags'])
      n.emit_compiler_rule('clang', target, flag_name='cflags',
                           extra_flags=extra_flags + ['$clangflags'])
    n.emit_compiler_rule('asm_with_preprocessing', target, flag_name='asmflags',
                         extra_flags=extra_flags + ['$gccflags'])
    n.emit_compiler_rule('asm', target, flag_name='asmflags',
                         supports_deps=False,
                         extra_flags=extra_flags + ['$gccflags'])
    n.emit_ar_rule('ar', target)
    for rule_suffix in ['', '_system_library']:
      n.emit_linker_rule('ld' + rule_suffix, target, 'ldflags')
      common_linkso_args = NinjaGenerator._get_target_ld_flags(
          target, is_so=True, is_system_library=bool(rule_suffix))
      n.rule('linkso%s.%s' % (rule_suffix, target),
             '%s -o $out %s' % (toolchain.get_tool(target, 'ld'),
                                common_linkso_args),
             description='linkso.%s $out' % target,
             rspfile='$out.files',
             rspfile_content='$in_newline')

    n.rule('prioritize_ctors',
           ('cp $in $out && ' +
            toolchain.get_tool(target, 'objcopy') +
            ' --rename-section .ctors=.ctors$ctors_suffix'
            ' --rename-section .rela.ctors=.rela.ctors$ctors_suffix '
            ' --rename-section .init_array=.init_array$init_array_suffix'
            ' --rename-section '
            '.rela.init_array=.rela.init_array$init_array_suffix '
            '$out'))

  @staticmethod
  def emit_host_rules_(n):
    n.emit_compiler_rule('cxx', 'host', flag_name='hostcxxflags')
    n.emit_compiler_rule('cc', 'host', flag_name='hostcflags')
    n.emit_compiler_rule('asm_with_preprocessing', 'host',
                         flag_name='hostasmflags')
    n.emit_compiler_rule('asm', 'host', flag_name='hostasmflags',
                         supports_deps=False)
    n.emit_ar_rule('ar', 'host')
    n.emit_linker_rule('ld', 'host', 'hostldflags')
    linkso_args = NinjaGenerator._get_target_ld_flags(
        'host', is_so=True, is_system_library=False)
    n.rule('linkso.host',
           '%s -o $out %s' % (toolchain.get_tool('host', 'ld'),
                              linkso_args),
           description='linkso.host $out',
           rspfile='$out.files',
           rspfile_content='$in_newline')

  @staticmethod
  def emit_common_rules(n):
    n.variable('asmflags', CNinjaGenerator.get_asmflags())
    n.variable('cflags', CNinjaGenerator.get_cflags())
    n.variable('cxxflags', CNinjaGenerator.get_cxxflags())
    n.variable('hostcflags', CNinjaGenerator.get_hostcflags())
    n.variable('hostcxxflags', CNinjaGenerator.get_hostcxxflags())

    # Native Client gcc seems to emit stack protector related symbol references
    # under some circumstances, but the related library does not seem to be
    # present in the NaCl toolchain.  Disabling for now.
    n.variable('naclflags', '-fno-stack-protector')

    # Allow Bionic's config.py to change crtbegin for libc.so. See
    # mods/android/bionic/config.py for detail.
    n.variable('crtbegin_for_so', build_common.get_bionic_crtbegin_so_o())

    CNinjaGenerator.emit_optimization_flags(n)
    n.variable('gccflags', ' '.join(CNinjaGenerator._get_gccflags()))
    n.variable('gxxflags',
               '$gccflags ' + ' '.join(CNinjaGenerator._get_gxxflags()))
    if toolchain.has_clang(OPTIONS.target()):
      n.variable('clangflags', ' '.join(CNinjaGenerator._get_clangflags()))
      n.variable('clangxxflags',
                 '$clangflags ' + ' '.join(CNinjaGenerator._get_clangxxflags()))

    CNinjaGenerator.emit_target_rules_(n)
    CNinjaGenerator.emit_host_rules_(n)

    if OPTIONS.is_nacl_build():
      # Native Client validation test
      n.rule('run_ncval_test',
             (toolchain.get_tool(OPTIONS.target(), 'ncval') +
              ' $in ' + build_common.get_test_output_handler()),
             description='NaCl validate $in')

  def _get_rule_name(self, rule_prefix):
    if self._notices_only:
      return 'phony'
    if self._is_host:
      return rule_prefix + '.host'
    return rule_prefix + '.' + OPTIONS.target()

  def _get_toc_file_for_so(self, so_file):
    if self._is_host:
      return so_file + '.TOC'
    basename_toc = os.path.basename(so_file) + '.TOC'
    return os.path.join(build_common.get_load_library_path(), basename_toc)

  def cxx(self, name, **kwargs):
    rule = 'clangxx' if self._enable_clang else 'cxx'
    return self.build(
        self.get_build_path(self.get_object_path(name)),
        self._get_rule_name(rule), name, **kwargs)

  def cc(self, name, **kwargs):
    rule = 'clang' if self._enable_clang else 'cc'
    return self.build(
        self.get_build_path(self.get_object_path(name)),
        self._get_rule_name(rule), name, **kwargs)

  def asm(self, name, **kwargs):
    return self.build(
        self.get_build_path(self.get_object_path(name)),
        self._get_rule_name('asm'), name, **kwargs)

  def asm_with_preprocessing(self, name, **kwargs):
    return self.build(
        self.get_build_path(self.get_object_path(name)),
        self._get_rule_name('asm_with_preprocessing'), name, **kwargs)

  def get_ncval_test_output(self, binfile):
    return binfile + '.ncval'

  def ncval_test(self, binfiles):
    for binfile in as_list(binfiles):
      self.build(self.get_ncval_test_output(binfile), 'run_ncval_test', binfile)

  def add_libchromium_base_compile_flags(self):
    self.add_include_paths('android/external/chromium_org')
    self.add_compiler_flags('-include', staging.as_staging(
        'src/common/chromium_build_config.h'))

  def add_ppapi_compile_flags(self):
    self.add_include_paths('chromium-ppapi',
                           'chromium-ppapi/ppapi/lib/gl/include',
                           'out/staging')

  def add_ppapi_link_flags(self):
    self.add_library_deps('libchromium_ppapi.a')

  def emit_logtag_flags(self):
    logtag = self._module_name
    self.add_defines(r'LOG_TAG="%s"' % logtag)

  # TODO(crbug.com/322776): Remove when these are detected properly by
  # make_to_ninja.py and emitted to each ninja file.
  def emit_globally_exported_include_dirs(self):
    paths = ['android/external/skia/include/config',
             'android/external/skia/include/core',
             'android/external/skia/include/effects',
             'android/external/skia/include/gpu',
             'android/external/skia/include/images',
             'android/external/skia/include/pdf',
             'android/external/skia/include/pipe',
             'android/external/skia/include/ports',
             'android/external/skia/include/utils',
             'android/external/skia/include/lazy',
             'android/ndk/sources/android/cpufeatures']
    self.add_include_paths(*paths)

  def emit_framework_common_flags(self):
    self.add_defines('NO_MALLINFO=1', 'SK_RELEASE')
    if OPTIONS.is_java_methods_logging():
      self.add_defines('LOG_JAVA_METHODS=1')
    paths = ['android/frameworks/av/include',
             'android/frameworks/base/core/jni',
             'android/frameworks/base/core/jni/android/graphics',
             'android/frameworks/base/include',
             'android/frameworks/base/libs/hwui',
             'android/frameworks/base/native/include',
             'android/frameworks/base/services',
             'android/frameworks/base/services/surfaceflinger',
             'android/frameworks/native/opengl/include',
             'android/frameworks/native/opengl/libs',
             'android/frameworks/native/include',
             'android/system/core/include',
             'android/libnativehelper/include',
             'android/libnativehelper/include/nativehelper',
             'android/external/harfbuzz_ng/src',
             'android/external/icu4c/common',
             'android/libcore/include',
             'android/hardware/libhardware/include',
             'android/external/skia/include',
             'android/external/skia/include/core',
             'android/external/skia/include/effects',
             'android/external/skia/include/images',
             'android/external/skia/include/utils',
             'android/external/skia/src/ports',
             'android/external/sqlite/android',
             'android/external/sqlite/dist']
    self.add_include_paths(*paths)

  def emit_ld_wrap_flags(self):
    ld_wrap_flags = ' '.join(['-Wl,--wrap=' + x for x
                              in wrapped_functions.get_wrapped_functions()])
    self.variable('ldflags', '$ldflags ' + ld_wrap_flags)

  def emit_gl_common_flags(self, hidden_visibility=True):
    self.add_defines('GL_GLEXT_PROTOTYPES', 'EGL_EGLEXT_PROTOTYPES')
    self.add_include_paths('android/bionic/libc/private')
    if hidden_visibility:
      self.add_cxx_flags('-fvisibility=hidden')

  def get_included_module_names(self):
    module_names = []
    for dep in self._static_deps + self._whole_archive_deps:
      module_name = dep
      if os.path.sep in module_name:
        module_name = os.path.splitext(os.path.basename(module_name))[0]
      if module_name == 'libgcc':
        # libgcc is not built for nacl mode and even in BMM where we generate
        # it, the code remains permissively licensed.
        continue
      module_names.append(module_name)
    return module_names


class RegenDependencyComputer(object):
  """This class knows which files, when changed, require rerunning configure."""

  def __init__(self):
    self._computed = False
    self._input = None
    self._output = None

  def _compute(self):
    # Any change to one of these files requires rerunning
    # configure.
    self._input = find_all_files(['src', 'mods'],
                                 filenames='config.py',
                                 use_staging=False,
                                 include_tests=True)

    self._input += [
        'src/build/DEPS.android-sdk',
        'src/build/DEPS.chrome',
        'src/build/DEPS.naclsdk',
        'src/build/DEPS.ndk',
        'src/build/build_common.py',
        'src/build/build_options.py',
        'src/build/config.py',
        'src/build/config_loader.py',
        'src/build/download_sdk_and_ndk.py',
        'src/build/make_to_ninja.py',
        'src/build/ninja_generator.py',
        'src/build/sync_nacl_sdk.py',
        'src/build/toolchain.py',
        'src/build/wrapped_functions.py',
        'third_party/android/build/target/product/core_base.mk']

    if not open_source.is_open_source_repo():
      self._input += [
          'src/packaging/runtime/active_window_back.png',
          'src/packaging/runtime/active_window_close.png',
          'src/packaging/runtime/active_window_extdir.png',
          'src/packaging/runtime/active_window_maximize.png',
          'src/packaging/runtime/active_window_minimize.png',
          'src/packaging/runtime/style.css']

    self._output = [OPTIONS.get_configure_options_file()]

    # We do not support running the downloaded or built Chrome with an ARM
    # target on a dev machine.  We do not download/build Chrome in the
    # open source repository.
    if not open_source.is_open_source_repo() and not OPTIONS.is_arm():
      self._output += [build_common.get_chrome_prebuilt_stamp_file()]

    # Remove the options_file from the list of output dependencies. The option
    # file is only written if it changes to avoid triggering subsequent builds,
    # but if we list it here and it is not actually written out it will trigger
    # the regeneration step every time as ninja will think it is out of date.
    self._output.remove(OPTIONS.get_configure_options_file())

  def get_output_dependencies(self):
    if not self._computed:
      self._compute()
    return self._output

  def get_input_dependencies(self):
    if not self._computed:
      self._compute()
    return self._input

  @staticmethod
  def verify_is_output_dependency(path):
    dependencies = \
        TopLevelNinjaGenerator._REGEN_DEPENDENCIES.get_output_dependencies()
    path = os.path.relpath(os.path.realpath(path), build_common.get_arc_root())
    if path not in dependencies:
      raise Exception('Please add %s to regen input dependencies' % path)

  @staticmethod
  def verify_is_input_dependency(path):
    dependencies = \
        TopLevelNinjaGenerator._REGEN_DEPENDENCIES.get_input_dependencies()
    path = os.path.relpath(os.path.realpath(path), build_common.get_arc_root())
    if path not in dependencies:
      raise Exception('Please add %s to regen input dependencies' % path)


class TopLevelNinjaGenerator(NinjaGenerator):
  """Encapsulate top-level ninja file generation."""

  _REGEN_DEPENDENCIES = RegenDependencyComputer()

  def __init__(self, module_name, generate_path=False, **kwargs):
    super(TopLevelNinjaGenerator, self).__init__(
        module_name, generate_path=generate_path, **kwargs)
    # Emit regeneration rules as high as possible in the top level ninja
    # so that if configure.py fails and writes a partial ninja file and
    # we fix configure.py, the regeneration rule will most likely be
    # in the partial build.ninja.
    self._emit_ninja_regeneration_rules()
    self._emit_common_rules()

  # TODO(crbug.com/177699): Improve ninja regeneration rule generation.
  def _emit_ninja_regeneration_rules(self):
    # Add rule/target to regenerate all ninja files we built this time
    # if configure.py changes.  We purposefully avoid specifying
    # the parameters to configure directly in the ninja file.  Otherwise
    # the act of running configure to change parameters generates
    # a ninja regeneration rule whose parameters differ, resulting in
    # ninja wanting to immediately re-run configure.
    self.rule('regen_ninja',
              'python $in $$(cat %s)' % OPTIONS.get_configure_options_file(),
              description='Regenerating ninja files due to dependency')
    # Use the paths from the regen computer, but transform them to staging
    # paths as we want to make sure we get mods/ paths when appropriate.
    input_dependencies = map(
        staging.third_party_to_staging,
        TopLevelNinjaGenerator._REGEN_DEPENDENCIES.get_input_dependencies())
    output_dependencies = (
        [self._ninja_path] +
        TopLevelNinjaGenerator._REGEN_DEPENDENCIES.get_output_dependencies())
    self.build(output_dependencies,
               'regen_ninja', 'src/build/configure.py',
               implicit=input_dependencies, use_staging=False)

  def _set_commonflags(self):
    self.variable('commonflags', CNinjaGenerator.get_commonflags())

  def _emit_common_rules(self):
    self._set_commonflags()

    ApkFromSdkNinjaGenerator.emit_common_rules(self)
    ApkNinjaGenerator.emit_common_rules(self)
    AtfNinjaGenerator.emit_common_rules(self)
    CNinjaGenerator.emit_common_rules(self)
    JarNinjaGenerator.emit_common_rules(self)
    JavaNinjaGenerator.emit_common_rules(self)
    NinjaGenerator.emit_common_rules(self)
    NoticeNinjaGenerator.emit_common_rules(self)
    PythonTestNinjaGenerator.emit_common_rules(self)
    TblgenNinjaGenerator.emit_common_rules(self)
    TestNinjaGenerator.emit_common_rules(self)

  def emit_subninja_rules(self, ninja_list):
    for ninja in ninja_list:
      if ninja._ninja_path != self.get_module_name():
        self.subninja(ninja._ninja_path)

  def emit_target_groups_rules(self, ninja_list):
    all_target_groups = _TargetGroups()

    # Build example APKs.
    all_target_groups.define_target_group('examples', 'default')
    # Run lint on all source files.
    all_target_groups.define_target_group('lint')

    for ninja in ninja_list:
      for build_rule in ninja._build_rule_list:
        all_target_groups.record_build_rule(*build_rule)
    all_target_groups.emit_rules(self)


class ArchiveNinjaGenerator(CNinjaGenerator):
  """Simple archive (static library) generator."""

  def __init__(self, module_name, instances=1,
               disallowed_symbol_files=None,
               **kwargs):
    super(ArchiveNinjaGenerator, self).__init__(
        module_name, ninja_name=module_name + '_a', **kwargs)
    if disallowed_symbol_files:
      self._disallowed_symbol_files = disallowed_symbol_files
    else:
      self._disallowed_symbol_files = ['disallowed_symbols.defined']
    self._instances = instances

  def archive(self, **kwargs):
    if self._shared_deps or self._static_deps or self._whole_archive_deps:
      raise Exception('Cannot use dependencies with an archive')
    archive_a = self.get_build_path(self._module_name + '.a')
    # Make sure |archive_a| does not contain a |_disallowed_symbol_files|
    # symbol, but the check is unnecessary for the host (i.e. it does not
    # matter if the disallowed symbols are included in the host library).
    if not self._notices_only and not self._is_host:
      self._check_symbols([archive_a], self._disallowed_symbol_files)
    return self.build(archive_a,
                      self._get_rule_name('ar'),
                      inputs=self._consume_objects(), **kwargs)

  @staticmethod
  def verify_usage_counts(archive_ninja_list,
                          shared_ninja_list, exec_ninja_list):
    usage_dict = collections.defaultdict(list)
    for ninja in shared_ninja_list + exec_ninja_list:
      for module_name in ninja.get_included_module_names():
        # Use is_host() in the key as the accounting should be done
        # separately for the target and the host.
        key = (module_name, ninja.is_host())
        usage_dict[key].append(ninja._module_name)

    error_list = []
    for ninja in archive_ninja_list:
      usage_list = usage_dict[(ninja._module_name, ninja.is_host())]
      if ninja.is_host():
        # For host archives, tracking the number of used count is not
        # important. We only check if an archive is used at least once.
        if usage_list:
          continue
        error_list.append('%s for host is not used' % ninja._module_name)
      else:
        if len(usage_list) == ninja._instances:
          continue
        error_list.append(
            '%s for target (allowed: %d, actual: %s)' % (
                ninja._module_name, ninja._instances, usage_list))
    if error_list:
      raise Exception(
          'Archives used unexpected number of times: ' + ', '.join(error_list))


class SharedObjectNinjaGenerator(CNinjaGenerator):
  """Create a shared object ninja file."""

  # Whether linking of new shared objects is enabled
  _ENABLED = True

  def __init__(self, module_name, install_path='/lib',
               disallowed_symbol_files=None,
               is_system_library=False, link_crtbegin=True, link_stlport=True,
               **kwargs):
    super(SharedObjectNinjaGenerator, self).__init__(
        module_name, ninja_name=module_name + '_so', **kwargs)
    # No need to install the shared library for the host.
    self._install_path = None if self._is_host else install_path
    if disallowed_symbol_files:
      self._disallowed_symbol_files = disallowed_symbol_files
    else:
      self._disallowed_symbol_files = ['libchromium_base.a.defined',
                                       'disallowed_symbols.defined']
    if not is_system_library:
      self.emit_ld_wrap_flags()
    self._is_system_library = is_system_library
    # For libc.so, we must not set syscall wrappers.
    if not is_system_library and not self._is_host:
      self._shared_deps.extend(
          build_common.get_bionic_shared_objects(link_stlport))
    self.installed_shared_library_list = []
    self._link_crtbegin = link_crtbegin

  @classmethod
  def disable_linking(cls):
    """Disables further linking of any shared libraries"""
    cls._ENABLED = False

  def _link_shared_object(self, output, inputs=None, variables=None,
                          allow_undefined=False, implicit=None, **kwargs):
    flag_variable = 'hostldflags' if self._is_host else 'ldflags'
    if not SharedObjectNinjaGenerator._ENABLED:
      raise Exception('Linking of additional shared libraries is not allowed')
    variables = self._add_lib_vars(as_dict(variables))
    if not self._link_crtbegin:
      variables['crtbegin_for_so'] = ''
    implicit = as_list(implicit) + self._static_deps + self._whole_archive_deps
    if self._notices_only:
      implicit += self._shared_deps
    else:
      implicit += map(self._get_toc_file_for_so, self._shared_deps)

    if not self._is_host:
      implicit.extend([build_common.get_bionic_crtbegin_so_o(),
                       build_common.get_bionic_crtend_so_o()])
      if OPTIONS.is_debug_code_enabled() and not self._is_system_library:
        implicit.append(build_common.get_bionic_libc_malloc_debug_leak_so())
    if not allow_undefined:
      CNinjaGenerator.add_to_variable(variables, flag_variable, '-Wl,-z,defs')
    soname = self._get_soname()
    # For the host, do not add -soname. If soname is added, LD_LIBRARY_PATH
    # needs to be set for runnning host executables, which is inconvenient.
    if not self._is_host:
      CNinjaGenerator.add_to_variable(variables, flag_variable,
                                      '-Wl,-soname=' + soname)
    rule_prefix = (
        'linkso_system_library' if self._is_system_library else 'linkso')
    return self.build(output, self._get_rule_name(rule_prefix), inputs,
                      variables=variables,
                      implicit=implicit, **kwargs)

  def _get_soname(self):
    return os.path.basename(self._module_name + '.so')

  def link(self, allow_undefined=True, **kwargs):
    # TODO(kmixter): Once we have everything in shared objects we
    # can make the default to complain if undefined references exist
    # in them.  Until then we silently assume they are all found
    # at run-time against the main plugin.
    basename_so = self._module_name + '.so'
    intermediate_so = self._link_shared_object(
        self.get_build_path(basename_so),
        self._consume_objects(),
        allow_undefined=allow_undefined,
        **kwargs)
    # When processing notices_only targets, short-circuit the rest of the
    # function to add logic to only one place instead of three (NaCl validation,
    # install, and symbol checking).
    # TODO(crbug.com/364344): Once Renderscript is built from source, remove.
    if self._notices_only:
      return intermediate_so
    if OPTIONS.is_nacl_build() and not self._is_host:
      self.ncval_test(intermediate_so)
    if self._install_path is not None:
      install_so = os.path.join(self._install_path, basename_so)
      self.install_to_build_dir(install_so, intermediate_so)
      self.installed_shared_library_list.append(install_so)

      # Create TOC file next to the installed shared library.
      self.build(self._get_toc_file_for_so(install_so),
                 'mktoc', self._rebase_to_build_dir(install_so),
                 implicit='src/build/make_table_of_contents.py')
    else:
      # Create TOC file next to the intermediate shared library if the shared
      # library is not to be installed. E.g. host binaries are not installed.
      self.build(self.get_build_path(basename_so + '.TOC'),
                 'mktoc', intermediate_so,
                 implicit='src/build/make_table_of_contents.py')

    # Make sure |intermediate_so| contain neither 'disallowed_symbols.defined'
    # symbols nor libchromium_base.a symbols, but the check is unnecessary for
    # the host (i.e. it does not matter if the disallowed symbols are included
    # in the host library).
    if OPTIONS.is_debug_info_enabled() and not self._is_host:
      self._check_symbols(intermediate_so, self._disallowed_symbol_files)
    return intermediate_so


class ExecNinjaGenerator(CNinjaGenerator):
  """ Create a binary ninja file."""

  _NACL_TEXT_SEGMENT_ADDRESS = '0x1000000'

  def __init__(self, module_name, install_path=None, is_system_library=False,
               **kwargs):
    super(ExecNinjaGenerator, self).__init__(module_name, **kwargs)
    # TODO(nativeclient:3734): We also use is_system_library
    # temporarily for building bare_metal_loader, but will stop using
    # it this way once that work is upstreamed.
    self._is_system_library = is_system_library
    self._install_path = install_path
    if not is_system_library and not self._is_host:
      if OPTIONS.is_arm():
        # On Bare Metal ARM, we need to expose all symbols in libgcc
        # so that NDK can use them.
        self._whole_archive_deps.extend(get_libgcc_for_bionic())
      else:
        self._static_deps.extend(get_libgcc_for_bionic())
      self._shared_deps.extend(build_common.get_bionic_shared_objects())

  def link(self, variables=None, implicit=None, **kwargs):
    implicit = as_list(implicit) + self._static_deps + self._whole_archive_deps
    if self._notices_only:
      implicit += self._shared_deps
    else:
      implicit += map(self._get_toc_file_for_so, self._shared_deps)

    if not self._is_host:
      implicit.extend([build_common.get_bionic_crtbegin_o(),
                       build_common.get_bionic_crtend_o()])
      if OPTIONS.is_debug_code_enabled() and not self._is_system_library:
        implicit.append(build_common.get_bionic_libc_malloc_debug_leak_so())
    variables = self._add_lib_vars(as_dict(variables))
    intermediate_bin = self.build(
        os.path.join(self._intermediates_dir,
                     self._module_name),
        self._get_rule_name(
            'ld_system_library' if self._is_system_library else 'ld'),
        self._consume_objects(),
        implicit=implicit,
        variables=variables,
        **kwargs)
    if OPTIONS.is_nacl_build() and not self._is_host:
      self.ncval_test(intermediate_bin)
    if self._install_path is not None:
      install_exe = os.path.join(self._install_path, self._module_name)
      self.install_to_build_dir(install_exe, intermediate_bin)
    return intermediate_bin

  @staticmethod
  def get_nacl_text_segment_address():
    return ExecNinjaGenerator._NACL_TEXT_SEGMENT_ADDRESS


class TblgenNinjaGenerator(NinjaGenerator):
  """Encapsulates ninja file generation for .td files using LLVM tblgen"""

  def __init__(self, module_name, **kwargs):
    super(TblgenNinjaGenerator, self).__init__(module_name, **kwargs)
    self._llvm_path = staging.as_staging('android/external/llvm')
    self._flags = ['-I=%s' % os.path.join(self._llvm_path, 'include')]

  def generate(self, output, arguments='-gen-intrinsic', arch=None):
    name = os.path.splitext(os.path.basename(output))[0]
    flags = self._flags
    if name == 'Intrinsics':
      source = os.path.join(self._llvm_path, 'include', 'llvm', 'IR',
                            'Intrinsics.td')
    else:
      assert arch, 'arch should be specified.'
      arch_include_path = os.path.join(self._llvm_path, 'lib/Target', arch)
      flags.append('-I=%s' % arch_include_path)
      source = os.path.join(arch_include_path, arch + '.td')
    implicit = [toolchain.get_tool(OPTIONS.target(), 'llvm_tblgen')]
    self.build(output, self._get_rule_name('llvm_tblgen'), source,
               variables={'flags': ' '.join(flags),
                          'arguments': arguments},
               implicit=implicit)

  @staticmethod
  def emit_common_rules(n):
    n.rule('llvm_tblgen',
           (toolchain.get_tool(OPTIONS.target(), 'llvm_tblgen') +
            ' $flags $in -o $out $arguments'),
           description='tblgen $in $out $arguments')

  def _get_rule_name(self, rule_prefix):
    if self._notices_only:
      return 'phony'
    return rule_prefix


# TODO(crbug.com/376952): Do licensing checks during build using ninja
# metadata to give us full information about included files.
class NoticeNinjaGenerator(NinjaGenerator):
  @staticmethod
  def emit_common_rules(n):
    # Concatenate a list of notice files into a file NOTICE file which
    # ends up being shown to the user.  We take care to show the path
    # to each notices file as it makes the notices more intelligible,
    # removing internal details like out/staging path prefix and our
    # ARC MOD TRACK markers that allow us to track a differently-named
    # notice file in upstream code.
    n.rule('notices_install',
           command='rm -f $out; (for f in $in; do echo;'
           'echo "==> $$f <==" | sed -e "s?out/staging/??g"; echo; '
           'grep -v "ARC MOD TRACK" $$f; done) > $out || '
           '(rm -f $out; exit 1)',
           description='notices_install $out')

    # Unpack and merge a notice tarball into final NOTICE_FILES tree.
    n.rule('notices_unpack',
           command='mkdir -p $out_dir && tar xf $in -C $out_dir && touch $out',
           description='notices_unpack $in')

  def _is_possibly_staged_path_open_sourced(self, path):
    """Check if the given path is open sourced, allowing for staging.

    We fall back to open_source module normally, but if in staging we have
    to fall back to the real path.  If we are given a directory in staging
    we only consider it open sourced if its third party and mods equivalents
    are both completely open sourced."""
    if path.startswith(build_common.get_staging_root()):
      path = staging.as_real_path(path)
      if path.startswith(build_common.get_staging_root()):
        third_party_path, mods_path = staging.get_composite_paths(path)
        return (open_source.is_open_sourced(third_party_path) and
                open_source.is_open_sourced(mods_path))
    return open_source.is_open_sourced(path)

  def _verify_open_sourcing(self, n, error_message):
    problem_examples = []
    for root in n.get_gpl_roots():
      raise Exception('GPL code is being binary distributed from %s' %
                      ','.join([n.get_license_root_example(r)
                               for r in n.get_gpl_roots()]))
    for root in n.get_source_required_roots():
      if not self._is_possibly_staged_path_open_sourced(root):
        problem_examples.append(n.get_license_root_example(root))
    if problem_examples:
      raise Exception('%s in %s' % (error_message,
                                    ','.join(n.get_source_required_examples())))

  def _build_notice(self, n, module_to_ninja_map, notice_files_dir):
    # Avoid updating n._notices with later add_notices call.
    notices = copy.deepcopy(n._notices)
    if OPTIONS.is_notices_logging():
      print 'Binary installed', n.get_module_name(), notices
    self._verify_open_sourcing(
        notices,
        '%s has targets in the binary distribution, is not open sourced, '
        'but has a restrictive license' % n._module_name)
    queue = n.get_included_module_names()
    # All included modules are now going to be binary distributed.  We need
    # to check that they are open sourced if required.  We also need to
    # check that they are not introducing a LGPL or GPL license into
    # a package that was not licensed with these.
    while queue:
      module_name = queue.pop(0)
      included_ninja = module_to_ninja_map[module_name]
      included_notices = included_ninja._notices
      if OPTIONS.is_notices_logging():
        print 'Included', module_name, included_notices
      self._verify_open_sourcing(
          included_notices,
          '%s has targets in the binary distribution, but %s has a '
          'restrictive license and is not open sourced' %
          (n._module_name, module_name))
      if included_notices.has_lgpl_or_gpl() and not notices.has_lgpl_or_gpl():
        logging.info('Included notices: %s' % included_notices)
        raise Exception(
            '%s (%s) cannot be included into %s (%s)' %
            (module_name, included_notices.get_most_restrictive_license_kind(),
             n._module_name, notices.get_most_restrictive_license_kind()))
      notices.add_notices(included_notices)
      queue.extend(included_ninja.get_included_module_names())
    notice_files = list(notices.get_notice_files())
    assert notice_files, 'Ninja %s has no associated NOTICE' % n._ninja_name
    notices_install_path = n.get_notices_install_path()
    notice_path = os.path.join(notice_files_dir, notices_install_path)
    self.build(notice_path, 'notices_install', notice_files)

  def _merge_notice_archive(self, n, module_to_ninja_map, notice_files_dir):
    assert not n.get_included_module_names()
    notices_stamp = os.path.join(build_common.get_target_common_dir(),
                                 n._module_name + '.notices.stamp')
    self.build(notices_stamp, 'notices_unpack', n.get_notice_archive(),
               variables={'out_dir': build_common.get_notice_files_dir()})

  def build_notices(self, ninja_list):
    """Generate NOTICE_FILES directory based on ninjas' notices and deps."""
    module_to_ninja_map = {}
    for n in ninja_list:
      module_to_ninja_map[n._module_name] = n

    notice_files_dir = build_common.get_notice_files_dir()

    for n in ninja_list:
      if not n.is_installed():
        continue
      if n.get_notice_archive():
        # TODO(crbug.com/366751): remove notice_archive hack when possible
        self._merge_notice_archive(n, module_to_ninja_map, notice_files_dir)
      else:
        self._build_notice(n, module_to_ninja_map, notice_files_dir)


class TestNinjaGenerator(ExecNinjaGenerator):
  """Create a googletest/googlemock executable ninja file."""

  def __init__(self, module_name, is_system_library=False, **kwargs):
    super(TestNinjaGenerator, self).__init__(
        module_name, is_system_library=is_system_library, **kwargs)
    if OPTIONS.is_bare_metal_build() and is_system_library:
      self.add_library_deps('libgtest_glibc.a', 'libgmock_glibc.a')
    else:
      self.add_library_deps('libgtest.a', 'libgmock.a',
                            'libcommon_test_main.a')
      self.add_library_deps('libchromium_base.a',
                            'libcommon.a',
                            'libpluginhandle.a')
    self.add_include_paths('third_party/testing/gmock/include')
    self._run_counter = 0
    self._disabled_tests = []
    self._qemu_disabled_tests = []
    if OPTIONS.is_arm():
      self._qemu_disabled_tests.append('*.QEMU_DISABLED_*')

  @staticmethod
  def _get_toplevel_run_test_variables():
    """Get the variables for running unit tests defined in toplevel ninja."""
    variables = {
        'runner': toolchain.get_tool(OPTIONS.target(), 'runner'),
        'valgrind_runner': toolchain.get_tool(OPTIONS.target(),
                                              'valgrind_runner'),
    }
    if OPTIONS.is_bare_metal_build() and OPTIONS.is_arm():
        variables['qemu_arm'] = ' '.join(toolchain.get_qemu_arm_args())
    return variables

  @staticmethod
  def _get_toplevel_run_test_rules():
    """Get the rules for running unit tests defined in toplevel ninja."""
    # rule name -> (command, test output handler, description)
    rules = {
        # NOTE: When $runner is empty, there will be an extra space in front of
        # the test invocation.
        'run_test': (
            '$runner $in $argv',
            build_common.get_test_output_handler(),
            'run_test $in'),
        'run_gtest': (
            '$runner $in $argv $gtest_options',
            build_common.get_test_output_handler(use_crash_analyzer=True),
            'run_gtest $in'),
        'run_gtest_with_valgrind': (
            '$valgrind_runner $in $argv $gtest_options',
            build_common.get_test_output_handler(),
            'run_gtest_with_valgrind $in')
    }
    if OPTIONS.is_bare_metal_build():
      rules['run_gtest_glibc'] = (
          '$qemu_arm $in $argv $gtest_options',
          build_common.get_test_output_handler(use_crash_analyzer=True),
          'run_gtest_glibc $in')
    return rules

  @staticmethod
  def emit_common_rules(n):
    variables = TestNinjaGenerator._get_toplevel_run_test_variables()
    for key, value in variables.iteritems():
      n.variable(key, value)
    rules = TestNinjaGenerator._get_toplevel_run_test_rules()
    for name, (command, output_handler, description) in rules.iteritems():
      n.rule(name, '%s %s' % (command, output_handler), description=description)

  def _save_test_info(self, test_path, counter, rule, variables):
    """Save information needed to run unit tests remotely as JSON file."""
    test_name = os.path.basename(test_path)
    rules = TestNinjaGenerator._get_toplevel_run_test_rules()
    merged_variables = TestNinjaGenerator._get_toplevel_run_test_variables()
    merged_variables.update(variables)
    merged_variables['in'] = test_path
    merged_variables['disabled_tests'] = ':'.join(self._disabled_tests)
    merged_variables['qemu_disabled_tests'] = ':'.join(
        self._qemu_disabled_tests)

    test_info = {
        'variables': merged_variables,
        'command': rules[rule][0],
    }
    filename = '%s.%d.json' % (test_name, counter)
    test_info_path = build_common.get_remote_unittest_info_path(filename)
    build_common.makedirs_safely(os.path.dirname(test_info_path))
    with open(test_info_path, 'w') as f:
      json.dump(test_info, f, indent=2, sort_keys=True)

  def find_all_contained_test_sources(self):
    all_sources = self.find_all_files(self._base_path,
                                      ['_test' + x
                                       for x in _PRIMARY_EXTENSIONS],
                                      include_tests=True)
    for basename in ['tests', 'test_util']:
      subdir = os.path.join(self._base_path, basename)
      if os.path.exists(subdir):
        all_sources += self.find_all_files(subdir, _PRIMARY_EXTENSIONS,
                                           include_tests=True)
    return list(set(all_sources))

  def build_default_all_test_sources(self):
    return self.build_default(self.find_all_contained_test_sources(),
                              base_path=None)

  def add_disabled_tests(self, *disabled_tests):
    """Add tests to be disabled."""
    self._disabled_tests += list(disabled_tests)

  def add_qemu_disabled_tests(self, *qemu_disabled_tests):
    """Add tests to be disabled only on QEMU."""
    self._qemu_disabled_tests += list(qemu_disabled_tests)

  def link(self, **kwargs):
    # Be very careful here.  If you have no objects because of
    # a path being wrong, the test will link and run successfully...
    # which is kind of bad if you really think about it.
    assert self._object_list, ('Module %s has no objects to link' %
                               self._module_name)
    return super(TestNinjaGenerator, self).link(**kwargs)

  def _get_test_rule_name(self, enable_valgrind):
    if enable_valgrind and OPTIONS.enable_valgrind():
      return 'run_gtest_with_valgrind'
    elif OPTIONS.is_bare_metal_build() and self._is_system_library:
      return 'run_gtest_glibc'
    else:
      return 'run_gtest'

  def run(self, tests, argv=None, enable_valgrind=True, implicit=None,
          rule=None):
    assert tests
    self._run_counter += 1
    if OPTIONS.run_tests():
      for test_path in tests:
        self._run_one(test_path, argv, enable_valgrind, implicit, rule)
    return self

  def _run_one(self, test_path, argv=None, enable_valgrind=True, implicit=None,
               rule=None):
    # TODO(crbug.com/378196): Create a script to build qemu-arm from stable
    # sources and run that built version here.
    if open_source.is_open_source_repo() and OPTIONS.is_arm():
      return
    variables = {}
    if argv:
      variables['argv'] = argv
    variables['gtest_options'] = '--gtest_color=yes'
    if self._disabled_tests or self._qemu_disabled_tests:
      variables['gtest_options'] += ' --gtest_filter=-' + ':'.join(
          self._disabled_tests + self._qemu_disabled_tests)

    implicit = as_list(implicit)
    # When you run a test, you need to install .so files.
    for deps in self._shared_deps:
      implicit.append(os.path.join(build_common.get_load_library_path(),
                                   os.path.basename(deps)))
    if OPTIONS.is_nacl_build() and not self._is_host:
      implicit.append(self.get_ncval_test_output(test_path))
    implicit.append(build_common.get_bionic_runnable_ld_so())
    if OPTIONS.is_bare_metal_build():
      implicit.append(build_common.get_bare_metal_loader())
    if OPTIONS.enable_valgrind():
      implicit.append('src/build/valgrind/memcheck/suppressions.txt')
    if not rule:
      rule = self._get_test_rule_name(enable_valgrind)
    self.build(test_path + '.results.' + str(self._run_counter), rule,
               inputs=test_path, variables=variables, implicit=implicit)

    self._save_test_info(test_path, self._run_counter, rule, variables)


class PpapiTestNinjaGenerator(TestNinjaGenerator):
  """Create a test executable that has PPAPI mocking. """

  def __init__(self, module_name, implicit=None, **kwargs):
    # Force an implicit dependency on libppapi_mocks.a in order to assure
    # that all of the auto-generated headers for the source files that
    # comprise that library are generated before any tests might want to
    # include them.
    libppapi_mocks_build_path = build_common.get_build_path_for_library(
        'libppapi_mocks.a')
    implicit = [libppapi_mocks_build_path] + as_list(implicit)
    super(PpapiTestNinjaGenerator, self).__init__(module_name,
                                                  implicit=implicit,
                                                  **kwargs)
    self.add_ppapi_compile_flags()
    self.add_ppapi_link_flags()
    # ppapi_mocks/background_thread.h uses Chromium's condition variable.
    self.add_libchromium_base_compile_flags()
    self.add_library_deps('libppapi_mocks.a')
    self.add_include_paths('src/ppapi_mocks',
                           self.get_ppapi_mocks_generated_dir())

  @staticmethod
  def get_ppapi_mocks_generated_dir():
    return os.path.join(build_common.get_build_dir(), 'ppapi_mocks')


# TODO(crbug.com/395058): JavaNinjaGenerator handles aapt processing, but
# it is Android specific rule and should be placed outside this class.
# It will be better that JarNinjaGenerator contains it and ApkNinjaGenerator
# inherits JarNinjaGenerator. Once we can remove canned jar files, and use
# make_to_ninja for existing some modules that use JarNinjaGenerator directly,
# JarNinjaGenerator can be renamed as JavaLibraryNinjaGenerator.
class JavaNinjaGenerator(NinjaGenerator):

  # Map from module name to path to compiled classes.
  _module_to_compiled_class_path = {}

  # Resource includes (passed to aapt) to use for all APKs.
  _default_resource_includes = []

  """Implements a simple java ninja generator."""
  def __init__(self, module_name, base_path=None,
               source_subdirectories=None, exclude_aidl_files=None,
               include_aidl_files=None, classpath_files=None,
               resource_subdirectories=None, resource_includes=None,
               resource_class_names=None, manifest_path=None,
               require_localization=False, aapt_flags=None, **kwargs):
    super(JavaNinjaGenerator, self).__init__(module_name, base_path=base_path,
                                             **kwargs)

    # Generate paths to all source code files (not just .java files)
    self._source_paths = [os.path.join(self._base_path or '', path)
                          for path in as_list(source_subdirectories)]

    exclude_aidl_files = frozenset(os.path.join(self._base_path, path)
                                   for path in as_list(exclude_aidl_files))
    self._exclude_aidl_files = exclude_aidl_files
    include_aidl_files = frozenset(os.path.join(self._base_path, path)
                                   for path in as_list(include_aidl_files))
    self._include_aidl_files = include_aidl_files

    # Specific information for the javac compiler.
    self._javac_source_files = []
    self._javac_stamp_files = []
    self._javac_source_files_hashcode = None
    self._javac_classpath_files = as_list(classpath_files)
    self._javac_classpath_dirs = []
    self._java_source_response_file = self._get_build_path(subpath='java.files')
    self._jar_files_to_extract = []

    self._resource_paths = []
    self._resource_includes = (JavaNinjaGenerator._default_resource_includes +
                               as_list(resource_includes))
    if resource_class_names is None:
      self._resource_class_names = ['R']
    else:
      self._resource_class_names = resource_class_names

    if resource_subdirectories is not None:
      self._resource_paths = [os.path.join(self._base_path or '', path)
                              for path in as_list(resource_subdirectories)]

    if manifest_path is None:
      manifest_path = 'AndroidManifest.xml'
    manifest_staging_path = staging.as_staging(
        os.path.join(self._base_path or '', manifest_path))
    if os.path.exists(manifest_staging_path):
      self._manifest_path = manifest_staging_path
    else:
      self._manifest_path = None

    self._require_localization = require_localization
    self._aapt_flags = aapt_flags

  @staticmethod
  def emit_common_rules(n):
    n.variable('aapt', toolchain.get_tool('java', 'aapt'))
    n.variable('aidl', toolchain.get_tool('java', 'aidl'))
    n.variable('dexopt', ('src/build/filter_dexopt_warnings.py ' +
                          toolchain.get_tool('java', 'dexopt')))
    n.variable('java-event-log-tags',
               toolchain.get_tool('java', 'java-event-log-tags'))
    n.variable('javac', ('src/build/filter_java_warnings.py ' +
                         toolchain.get_tool('java', 'javac')))
    n.variable('jflags', ('-J-Xmx512M -target 1.5 -Xmaxerrs 9999999 '
                          '-encoding UTF-8 -g'))
    n.variable('aidlflags', '-b')
    n.variable('aaptflags', '-x -m')

    n.rule('javac',
           ('rm -rf $out_class_path && '
            'mkdir -p $out_class_path && '
            '$javac $jflags @$response_file -d $out_class_path && '
            'touch $out'),
           description='javac $module_name ($count files)',
           rspfile='$response_file',
           rspfile_content='$in_newline')
    n.rule('aidl',
           '$aidl -d$out.d $aidlflags $in $out',
           depfile='$out.d',
           description='aidl $out')
    # Aapt is very loud about warnings for missing comments for public
    # symbols that we cannot suppress.  Only show these when there is an
    # actual error.  Note also that we do not use the
    # --generate-dependencies flag to aapt.  While it does generate a
    # Makefile-style dependency file, that file will have multiple
    # targets and ninja does not support depfiles with multiple targets.
    n.rule('aapt_package',
           (toolchain.get_tool('java', 'aapt') +
            ' package $aaptflags -M $manifest ' +
            '$input_path > $tmpfile 2>&1 || ' +
            '(cat $tmpfile; exit 1)'),
           description='aapt package $out')
    n.rule('llvm_rs_cc',
           ('LD_LIBRARY_PATH=$toolchaindir '
            '$toolchaindir/llvm-rs-cc -o $resout -p $srcout $args '
            '-I $clangheader -I $scriptheader $in > $log 2>&1 || '
            '(cat $log; rm $log; exit 1)'),
           description='llvm-rs-cc $resout $srcout')
    n.rule('aapt_remove_file',
           ('cp $in $out && $aapt remove $out $targets'),
           description='aapt remove $targets from $out')
    n.rule('eventlogtags',
           '$java-event-log-tags -o $out $in /dev/null',
           description='eventlogtag $out')
    n.rule('dex_preopt',
           ('rm -f $out; '
            'BOOTCLASSPATH=$bootclasspath '
            '$dexopt --preopt $in $out "$dexflags" $warning_grep'),
           description='dex_preopt $out')
    n.rule('create_multidex_zip',
           'DIR=$$(mktemp -d --tmpdir=out); ' +
           '(cd $$DIR && ' +
           'unzip -q -o ../../$in $dexname && ' +
           'mv -f $dexname classes.dex && ' +
           'rm -f ../../$out && ' +
           'zip -q ../../$out classes.dex); ' +
           'rm -f $$DIR/classes.dex && rmdir $$DIR || (rm $out; exit 1)',
           description='creating multidex zip $out')

  @staticmethod
  def add_default_resource_include(resource_include):
    JavaNinjaGenerator._default_resource_includes.append(
        resource_include)

  def add_built_jars_to_classpath(self, *jars):
    self._javac_classpath_files.extend([
        build_common.get_build_path_for_jar(jar, subpath='classes.jar')
        for jar in jars])

  def _add_java_files(self, java_files):
    if not java_files:
      return

    # Transform all paths to be relative to staging.
    java_files = [staging.as_staging(java_file) for java_file in java_files]

    self._javac_source_files_hashcode = None
    self._javac_stamp_files = []
    self._javac_source_files.extend(java_files)
    return self

  def add_java_files(self, files, base_path=''):
    if base_path is not None:
      if base_path == '':
        base_path = self._base_path
      files = [os.path.join(base_path, f) for f in files]
    self._add_java_files(files)

  @staticmethod
  def _extract_pattern_as_java_file_path(path, pattern, class_name=None,
                                         extension='.java',
                                         ignore_dependency=False):
    """Extracts a dotted package name using the indicated pattern from a file.
    Converts the dotted package name to a relative file path, which is then
    returned."""
    package_name = _extract_pattern_from_file(path, pattern, ignore_dependency)
    package_path = package_name.replace('.', '/')
    if class_name is None:
      # Take the name of the file we read from as the name of the class that it
      # represents.
      class_name = os.path.splitext(os.path.split(path)[1])[0]
    return os.path.join(package_path, class_name + extension)

  @staticmethod
  def _change_extension(path, new_extension, old_extension=None):
    """Change the extension on the path to new_extension. If old_extension is
    given, the given path's extension must match first."""
    base, ext = os.path.splitext(path)
    if old_extension and ext == old_extension:
      return base + new_extension
    return path

  def _get_source_files_hashcode(self):
    if self._javac_source_files_hashcode is None:
      real_srcs = ' '.join(staging.as_real_path(src_path) for src_path in
                           self._javac_source_files)
      self._javac_source_files_hashcode = _compute_hash_fingerprint(real_srcs)
    return self._javac_source_files_hashcode

  def _get_compiled_class_path(self):
    # We have a computed intermediate path for the .class files, based on the
    # hash of all the "real" paths of all the source files. That way if even
    # a single file is overlaid (or un-overlaid), all previous intermediates
    # for the jar are invalidated.  This function must not be called until
    # all source files are added.
    return self._get_build_path(subpath=self._get_source_files_hashcode())

  def _get_stamp_file_path_for_compiled_classes(self):
    return self._get_build_path(subpath=(self._get_source_files_hashcode() +
                                         '.javac.stamp'))

  @staticmethod
  def get_compiled_class_path_for_module(module):
    return JavaNinjaGenerator._module_to_compiled_class_path[module]

  def _build_eventlogtags(self, output_path, input_file):
    # To properly map the logtag inputs to outputs, we need to know the
    # package name.
    re_pattern = 'option java_package ([^;\n]+)'
    java_path = JavaNinjaGenerator._extract_pattern_as_java_file_path(
        input_file, re_pattern, ignore_dependency=True)
    output_file = os.path.join(output_path, java_path)
    return self.build([output_file], 'eventlogtags', inputs=[input_file])

  def _build_aidl(self, output_path, input_file):
    # To properly map the aidl inputs to outputs, we need to know the
    # package name.
    re_pattern = 'package (.+);'
    java_path = JavaNinjaGenerator._extract_pattern_as_java_file_path(
        input_file, re_pattern, ignore_dependency=True)
    output_file = os.path.join(output_path, java_path)
    return self.build([output_file], 'aidl', inputs=[input_file])

  def _build_javac(self, implicit=None):
    if implicit is None:
      implicit = []
    jflags = _VariableValueBuilder('jflags')
    jflags.append_optional_path_list('-bootclasspath',
                                     self._get_minimal_bootclasspath())
    jflags.append_optional_path_list('-classpath',
                                     self._javac_classpath_files +
                                     self._javac_classpath_dirs)

    java_source_files = sorted(self._javac_source_files)

    if not java_source_files:
      raise Exception('No Java source files specified')

    variables = dict(out_class_path=self._get_compiled_class_path(),
                     response_file=self._java_source_response_file,
                     count=len(java_source_files),
                     module_name=self._module_name,
                     jflags=jflags)

    self._module_to_compiled_class_path[self._module_name] = (
        self._get_compiled_class_path())

    self._javac_stamp_files.append(
        self._get_stamp_file_path_for_compiled_classes())
    return self.build(self._javac_stamp_files, 'javac',
                      inputs=java_source_files,
                      implicit=(self._get_minimal_bootclasspath() +
                                self._javac_classpath_files +
                                implicit),
                      variables=variables)

  def _build_aapt(self, outputs=None, output_apk=None, inputs=None,
                  implicit=None, input_path=None, out_base_path=None):
    outputs = as_list(outputs)
    implicit = as_list(implicit)

    resource_paths = [staging.as_staging(path)
                      for path in as_list(self._resource_paths)]

    aaptflags = _VariableValueBuilder('aaptflags')
    aaptflags.append_flag('-f')
    if self._require_localization:
      aaptflags.append_flag('-z')
    aaptflags.append_flag_pattern('-S %s', resource_paths)
    if self._resource_includes:
      aaptflags.append_flag_pattern('-I %s', self._resource_includes)

    if out_base_path:
      aaptflags.append_flag('-m')
      aaptflags.append_flag('-J ' + out_base_path)

    if output_apk:
      aaptflags.append_flag('-F ' + output_apk)
      outputs.append(output_apk)

    if self._aapt_flags:
      aaptflags.append_flag(self._aapt_flags)

    implicit += [self._manifest_path]
    implicit += as_list(self._resource_includes)

    variables = dict(
        aaptflags=aaptflags,
        input_path=input_path or '',
        manifest=self._manifest_path,
        tmpfile=self._get_build_path(subpath='aapt_errors'))

    return self.build(outputs=outputs, rule='aapt_package', inputs=inputs,
                      implicit=implicit, variables=variables)

  def _build_llvm_rs_cc(self):
    """Generates renderscript source code and llvm bit code if exists.

    This function does nothing and returns empty array if there is no
    renderscript source files.
    """
    input_files = self.find_all_files(
        base_paths=[self._base_path], suffix=['rs'])
    if not input_files:
      return []

    intermediate_dir = build_common.get_build_path_for_apk(self._module_name)
    rsout_dir = os.path.join(intermediate_dir, 'src', 'renderscript')
    rsout_resdir = os.path.join(rsout_dir, 'res', 'raw')

    rsout_res_files = []
    for f in input_files:
      basename = re.sub('\.rs$', '.bc', os.path.basename(f))
      rsout_res_files.append(os.path.join(rsout_resdir, basename))
    # The output files have "ScriptC_" prefix, e.g. gray.rs will be converted to
    # ScriptC_gray.java.
    rsout_src_files = []
    for f in input_files:
      basename = re.sub('^(.*)\.rs$', r'ScriptC_\1.java', os.path.basename(f))
      directory = os.path.dirname(f.replace(self._base_path, rsout_dir))
      rsout_src_files.append(os.path.join(directory, basename))

    variables = {
        'log': os.path.join(intermediate_dir, 'build.log'),
        'toolchaindir': toolchain.get_android_sdk_build_tools_dir(),
        'resout': rsout_resdir,
        'srcout': os.path.join(rsout_dir, 'src'),
        'args': '-target-api 18 -Wall '
                '-Werror -rs-package-name=android.support.v8.renderscript',
        'clangheader': toolchain.get_clang_include_dir(),
        'scriptheader': os.path.join('third_party', 'android', 'frameworks',
                                     'rs', 'scriptc')
    }
    self.add_generated_files(base_paths=[], files=rsout_src_files)
    self.add_resource_paths([os.path.join(build_common.get_arc_root(),
                                          os.path.dirname(rsout_resdir))])
    # Needed for packaging multiple resources.
    self.add_flags('aaptflags', '--auto-add-overlay')

    return self.build(rsout_res_files + rsout_src_files, 'llvm_rs_cc',
                      input_files, variables=variables)

  def _build_and_add_all_generated_sources(self, implicit=None):
    # |implicit| is unused here but it is used in the inherited class.
    self.build_and_add_logtags()
    self.build_and_add_aidl_generated_java()

  def build_and_add_resources(self, implicit=None):
    """Emits a build rule to process the resource files, generating R.java, and
    adds the generated file to the list to include in the package."""

    # Skip if we don't appear to be configured to have any resources.
    if not self._resource_paths or not self._manifest_path:
      return

    if implicit is None:
      implicit = []

    resource_files = self.find_all_files(self._resource_paths, ['.xml'])
    resource_files = [staging.as_staging(path) for path in resource_files]
    self.add_notice_sources(resource_files)

    out_resource_path = self._get_build_path(subpath='R')

    # Attempt to quickly extract the value of the package name attribute from
    # the manifest, without resorting to an actual XML parser.
    re_pattern = 'package="(.+?)"'

    java_files = []
    for c in self._resource_class_names:
      java_path = JavaNinjaGenerator._extract_pattern_as_java_file_path(
          self._manifest_path, re_pattern, class_name=c, ignore_dependency=True)
      java_files.append(os.path.join(out_resource_path, java_path))

    self._build_aapt(outputs=java_files, implicit=resource_files + implicit,
                     out_base_path=out_resource_path)

    self._add_java_files(java_files)

    return self

  def build_and_add_logtags(self, logtag_files=None):
    """Emits code to convert .logtags to .java, and adds the generated .java
    files to the list to include in the package."""
    if logtag_files is None:
        logtag_files = self.find_all_files(self._source_paths, ['.logtags'])

    logtag_files = [staging.as_staging(logtag_file)
                    for logtag_file in logtag_files]
    out_eventlog_path = self._get_build_path(subpath='eventlogtags')

    java_files = []
    for logtag_file in logtag_files:
      java_files += self._build_eventlogtags(output_path=out_eventlog_path,
                                             input_file=logtag_file)

    self._add_java_files(java_files)

  def build_and_add_aidl_generated_java(self):
    """Emits code to convert .aidl to .java, and adds the generated .java files
    to the list to include in the package."""
    aidl_files = []
    all_aidl_files = self.find_all_files(self._source_paths, ['.aidl'])
    all_aidl_files.extend(staging.as_staging(x)
                          for x in self._include_aidl_files)

    for aidl_file in all_aidl_files:
      if aidl_file not in self._exclude_aidl_files:
        aidl_file = staging.as_staging(aidl_file)
        with open_dependency(aidl_file, 'r', ignore_dependency=True) as f:
          if not re.search('parcelable', f.read()):
            aidl_files.append(aidl_file)

    aidl_files = [staging.as_staging(x) for x in aidl_files]

    out_aidl_path = self._get_build_path(subpath='aidl')

    # For any package, all the aidl invocations should have the same include
    # path arguments, so emit it directly to the subninja.
    aidlflags = _VariableValueBuilder('aidlflags')
    aidlflags.append_flag_pattern('-I%s', [staging.as_staging(path)
                                           for path in self._source_paths])
    self.variable('aidlflags', aidlflags)

    java_files = []
    for aidl_file in aidl_files:
      java_files += self._build_aidl(output_path=out_aidl_path,
                                     input_file=aidl_file)

    self._add_java_files(java_files)

  def add_aidl_flags(self, *flags):
    self.add_flags('aidlflags', *flags)
    return self

  def add_aidl_include_paths(self, *paths):
    self.add_aidl_flags(*['-I' + staging.as_staging(x) for x in paths])
    return self

  def add_all_java_sources(self, include_tests=False,
                           exclude_source_files=None):
    """Adds the default java source code found in the source paths to the list
    to include in the list of sources to be built."""
    return self._add_java_files(self.find_all_files(
        self._source_paths,
        ['.java'],
        exclude=exclude_source_files,
        include_tests=include_tests))

  def add_generated_files(self, base_paths, files):
    """Adds other generated source files to the list of sources to be built."""
    base_paths = [staging.as_staging(base_path) for base_path in base_paths]
    return self._add_java_files(files)

  def add_extracted_jar_contents(self, *jar_files):
    """Embeds jar_files into the current target (either a jar file or an apk
    package) to emulate Android.mk's LOCAL_STATIC_JAVA_LIBRARIES=."""
    self._jar_files_to_extract.extend(jar_files)
    self.add_built_jars_to_classpath(*jar_files)

  def _get_stamp_file(self, jar_file):
    return self._get_build_path(subpath=(self._get_source_files_hashcode() +
                                         '.' + jar_file + '.unzip.stamp'))

  def _extract_jar_contents(self):
    stamp_files = []
    for index, jar_file in enumerate(self._jar_files_to_extract):
      unzip_stamp_file = self._get_stamp_file(jar_file)
      implicit = self._javac_stamp_files
      if index > 0:
        # Add the previous stamp file to implicit to serialize the series of
        # unzip operations. With this, in case when two or more jar files
        # have exactly the same .class file, the last jar file's is used in
        # a deterministic manner.
        # TODO(yusukes): Check if this is really necessary.
        previous_unzip_stamp_file = self._get_stamp_file(
            self._jar_files_to_extract[index - 1])
        implicit.append(previous_unzip_stamp_file)
      # We unzip into the same directory as was used for compiling
      # java files unique to this jar.  The implicit dependency makes sure
      # that we do not unzip until all compilation is complete (as the
      # compilation blows away this directory and recreates it).
      self.build(unzip_stamp_file, 'unzip',
                 build_common.get_build_path_for_jar(
                     jar_file, subpath='classes.jar'),
                 implicit=implicit,
                 variables={'out_dir': self._get_compiled_class_path()})
      stamp_files.append(unzip_stamp_file)
    return stamp_files

  def build_all_added_sources(self, implicit=None):
    """Compiles the java code into .class files."""
    if implicit is None:
      implicit = []
    self._build_javac(implicit=implicit)
    return self

  def build_default_all_sources(self, include_tests=False,
                                exclude_source_files=None,
                                implicit=None):
    """Find and builds all generated and explicit sources, generating .class
    files."""
    if exclude_source_files is None:
      # Any package-info.java is expected to be an almost empty file with just
      # a package declaration, and which does not generate a .class file when
      # compiled with javac.
      exclude_source_files = ['package-info.java']

    if implicit is None:
      implicit = []
    implicit = implicit + self._build_llvm_rs_cc()
    self._build_and_add_all_generated_sources(implicit=implicit)
    self.add_all_java_sources(include_tests=include_tests,
                              exclude_source_files=exclude_source_files)
    return self.build_all_added_sources(implicit=implicit)

  def _get_sentinel_install_path(self, install_path):
    """Generate a sentinel path for use with dexopt.

    A sentinel path is passed to dexopt to indicate both the
    build-time path and run-time path of a file with one string.  A
    "/./" path element indicates the division point.  So the sentinel
    path to /system/framework/foo.jar would be
    out/target/$TARGET/root/./system/framework/foo.jar.

    See dalvik/vm/Misc.h for more info on sentinel paths.
    """
    return build_common.get_android_fs_path('.' + install_path)

  def _pre_dexopt_secondary_dex_files(self, secondary_dex_files,
                                      dexopt_variables, implicit_deps,
                                      multidex_output_dir):
    """Perform dexopt to Multidex dex files and install them.

    This emulates Multidex library's behavior at build time.  Multidex extracts
    classes$N.dex files from the apk to zip files (which are valid jar files),
    and puts the zip files into Dalvik's classpath.  If the zip file is new or
    updated, Dalvik will dexopt it.

    To avoid running slow dexopt at run time, here is the alternative at build
    time:
      1. Create zip files that contain the only dex to be optimized.
      2. Pre-dexopt the zip files and generate corresponding odex files.
      3. Install both zip and odex files to multidex_output_dir, so that
         Multidex library can pick up at run time.
    """
    for dexname in secondary_dex_files:
      base, _ = os.path.splitext(dexname)
      output_filename = '%s.apk.%s' % (self._module_name, base)

      # File names have to match Multidex's expectation.
      output_zip = self._get_build_path(
          os.path.join(dexname, output_filename + '.zip'))
      output_odex = self._get_build_path(
          os.path.join(dexname, output_filename + '.odex'))

      self.build(output_zip, 'create_multidex_zip', self._aligned_apk_archive,
                 variables={'dexname': dexname})
      self.build(output_odex, 'dex_preopt', output_zip,
                 variables=dexopt_variables,
                 implicit=implicit_deps)

      for filepath in [output_odex, output_zip]:
        self.install_to_root_dir(os.path.join(multidex_output_dir,
                                              os.path.basename(filepath)),
                                 filepath)

  def _build_odex_and_stripped_javalib(self, output_odex, output_javalib,
                                       input_zip, install_jar=None,
                                       implicit=None, secondary_dex_files=None,
                                       multidex_output_dir=None):
    """Run dex preoptimization, generating odex and javalib files.

    input_zip is either a jar file or an apk file.  This step does not
    install the output files, but takes install_jar in order to
    properly generate a bootclasspath (to account for edge cases of
    building dexopt'd jars in the middle of the bootclasspath).  If
    this is an apk or this jar is not installed, install_jar should be
    None.
    """
    if implicit is None:
      implicit = []
    bootclasspath = []
    # Build implicit and bootclasspath at the same time.
    for p in _BootclasspathComputer.get_installed_jars():
      if not p.startswith('/system'):
        raise Exception('BOOTCLASSPATH doesn\'t start with /system: ' + p)
      if install_jar and p == install_jar:
        # Avoid dependencies on self or anything in bootclasspath
        # including self and later.
        break
      jar_path = build_common.get_android_fs_path(p)
      implicit.append(jar_path)
      # Make sure the earlier .odex files are also implicit
      # dependencies of dex_preopt.
      implicit.append(JavaNinjaGenerator._change_extension(jar_path, '.odex',
                                                           '.jar'))
      bootclasspath.append(self._get_sentinel_install_path(p))

    dexopt = os.path.relpath(toolchain.get_tool('java', 'dexopt'),
                             build_common.get_arc_root())
    implicit.append(staging.third_party_to_staging(dexopt))

    dexopt_variables = {
        'dexflags': ('v=a,'   # Verify all
                     'o=v,'   # Optimize == verify
                     'm=y,'   # Map registers
                     'u=n'),  # No uniprocessor assumptions
        'bootclasspath': ':'.join(bootclasspath)}
    self.build(output_odex, 'dex_preopt',
               input_zip,
               variables=dexopt_variables,
               implicit=implicit)
    targets = ['classes.dex']

    # Runs additional dex preopt for APKs that use Multidex.
    if secondary_dex_files:
      targets.extend(secondary_dex_files)

      # Update classpath for classes$n.dex to refer to classes.odex.
      dexopt_variables['bootclasspath'] += (
          ':' + self._get_sentinel_install_path(
              os.path.join(self._install_path, os.path.basename(output_odex))))
      implicit.append(output_odex)

      self._pre_dexopt_secondary_dex_files(secondary_dex_files,
                                           dexopt_variables,
                                           implicit, multidex_output_dir)

    self.build(output_javalib, 'aapt_remove_file',
               input_zip,
               variables={'targets': ' '.join(targets)},
               implicit=staging.third_party_to_staging(
                   toolchain.get_tool('java', 'aapt')))

  def get_included_module_names(self):
    module_names = []
    for dep in self._jar_files_to_extract:
      module_name = dep
      if os.path.sep in module_name:
        module_name = os.path.splitext(os.path.basename(module_name))[0]
      module_names.append(module_name)
    return module_names


class JarNinjaGenerator(JavaNinjaGenerator):
  def __init__(self, module_name, install_path=None, dex_preopt=True,
               canned_jar_dir=None, core_library=False, java_resource_dirs=None,
               static_library=False, jar_packages=None, jarjar_rules=None,
               dx_flags=None, built_from_android_mk=False, **kwargs):
    # TODO(crbug.com/393099): Once all rules are generated via make_to_ninja,
    # |core_library| can be removed because |dx_flags| translated from
    # LOCAL_DX_FLAGS in Android.mk is automatically set to the right flag.
    super(JarNinjaGenerator, self).__init__(module_name,
                                            ninja_name=module_name + '_jar',
                                            **kwargs)
    assert (not static_library or not dex_preopt)
    assert (not core_library or not dx_flags), (
        'core_library and dx_flags can not be set simultaneously')
    self._install_path = install_path

    # TODO(crbug.com/390856): Remove |canned_jar_dir|.
    self._canned_jar_dir = canned_jar_dir
    self._output_pre_jarjar_jar = self._get_build_path(
        subpath='classes-full-debug.jar')
    self._output_classes_jar = self._get_build_path(subpath='classes.jar')
    self._output_javalib_jar = self._get_build_path(subpath='javalib.jar')
    self._output_javalib_noresources_jar = self._get_build_path(
        subpath='javalib_noresources.jar')
    if dex_preopt:
      self._output_odex_file = self._get_build_path(
          is_target=True,
          subpath='javalib.odex')
    else:
      self._output_odex_file = None

    self._is_core_library = core_library
    self._java_resource_dirs = [os.path.join(self._base_path, path)
                                for path in as_list(java_resource_dirs)]
    self._is_static_library = static_library

    self._jar_packages = jar_packages
    self._jar_stamp_file_dependencies = []

    # Note that the javalib.jar which has no dex really is not target
    # specific, but upstream Android build system puts it under target,
    # so we follow their example.
    self._output_jar = self._get_build_path(
        is_target=dex_preopt,
        subpath='javalib.jar')

    self._install_jar = None
    if self._install_path:
      self._install_jar = os.path.join(self._install_path,
                                       self._module_name + '.jar')

    self._jarjar_rules = jarjar_rules
    self._dx_flags = dx_flags
    self._built_from_android_mk = built_from_android_mk

  @staticmethod
  def emit_common_rules(n):
    n.variable('dx', toolchain.get_tool('java', 'dx'))
    n.variable('dxflags', '-JXms16M -JXmx1536M --dex')
    n.variable('jar', toolchain.get_tool('java', 'jar'))
    n.variable('jarjar', toolchain.get_tool('java', 'jarjar'))
    n.variable('java', toolchain.get_tool('java', 'java'))

    # ARC uses a system default cp command instead of 'acp' provided in
    # android/build/tools/acp/ to avoid an unnecessary tool build.
    n.rule('acp', 'mkdir -p $out_dir && cp -fp $in $out',
           description='mkdir -p $out_dir && cp -fp $in $out')
    n.rule('jar',
           '$jar -cf $out -C $in_class_path .',
           description='jar $out')
    n.rule('jar_update',
           '(cp $in $out && $jar -uf $out $jar_command) || (rm $out; exit 1)',
           description='jar_update $out')
    n.rule('jarjar',
           '$java -jar $jarjar process $rules $in $out',
           description='java -jar jarjar.jar process $rules $in $out')
    n.rule('unzip',
           'unzip -qou $in -d $out_dir && touch $out',
           description='unzip $in to $out_dir')
    n.rule('remove_non_matching_files',
           ('(set -f && find $in_dir -mindepth 1 -type d '
            '`for i in $match; do echo -not -path $in_dir/\\$$i; '
            'done` | xargs rm -rf && set +f && touch $out) || '
            '(rm $out; set +f; exit 1)'),
           description='removing files not matching $in_dir/$match')
    n.rule('dx',
           '$dx $dxflags --output=$out $in_path',
           description='dx $out')

  def _get_build_path(self, subpath=None, is_target=False):
    return build_common.get_build_path_for_jar(self._module_name,
                                               subpath=subpath,
                                               is_target=is_target)

  def _get_minimal_bootclasspath(self):
    """Provides a minimal bootclasspath for building these java files.

    The bootclasspath defines the core library and other required class
    files that every Java file will have access to.  Without providing
    a -bootclasspath option, the Java compiler would instead consult its
    built-in core libraries, whereas Android uses a separate Apache
    core library (as well as API frameworks, etc).  When compiling, every jar
    in the bootclasspath must be found and fully compiled (not being built
    in parallel).  This means that we need to set up implicit dependencies,
    and it also means that we must build the jars in the bootclasspath
    sequentially in the order of the bootclasspath.  The minimal
    bootclasspath is thus the entire bootclasspath when generating
    code for non-bootclasspath jars, or if generating for a bootclasspath
    jar, the bootclasspath up until that jar.
    """
    if self._built_from_android_mk:
      # Returns only core's classes.jar as the real Android build does.
      # This is calculated in android/build/core/base_rules.mk.
      core = _BootclasspathComputer.get_classes()[0]
      assert build_common.get_build_path_for_jar(
          'core', subpath='classes.jar') == core
      # On building core, it should not depend on core itself.
      return _truncate_list_at([core], self._output_classes_jar)

    if self._module_name == 'framework-base':
      return _truncate_list_at(_BootclasspathComputer.get_classes(),
                               build_common.get_build_path_for_jar(
                                   'framework',
                                   subpath='classes.jar'))
    return _truncate_list_at(_BootclasspathComputer.get_classes(),
                             self._output_classes_jar)

  def _build_classes_jar(self):
    if self._canned_jar_dir:
      self.build(self._output_classes_jar, 'cp',
                 os.path.join(self._canned_jar_dir, 'classes.jar'))
      return
    variables = dict(in_class_path=self._get_compiled_class_path())
    implicit = self._javac_stamp_files
    implicit.extend(self._extract_jar_contents())
    if self._jar_packages:
      jar_packages_stamp_file = self._get_build_path(
          subpath=(self._get_source_files_hashcode() + '.jar_packages.stamp'))
      in_dir = self._get_build_path(subpath=self._get_source_files_hashcode())
      self.build(jar_packages_stamp_file, 'remove_non_matching_files',
                 implicit=implicit,
                 variables={'match': self._jar_packages,
                            'in_dir': in_dir})
      implicit.append(jar_packages_stamp_file)
    if self._jarjar_rules:
      self.build([self._output_classes_jar], 'jarjar',
                 inputs=[self._output_pre_jarjar_jar],
                 implicit=[self._jarjar_rules],
                 variables={'rules': self._jarjar_rules})
      output_classes_jar = self._output_pre_jarjar_jar
    else:
      output_classes_jar = self._output_classes_jar
    return self.build([output_classes_jar], 'jar',
                      implicit=implicit,
                      variables=variables)

  def _build_javalib_jar_from_classes_jar(self):
    variables = {'in_path': self._output_classes_jar}
    if self._is_core_library:
      variables['dxflags'] = '$dxflags --core-library'
    if self._dx_flags:
      variables['dxflags'] = '$dxflags ' + self._dx_flags
    if self._java_resource_dirs:
      dx_out = [self._output_javalib_noresources_jar]
    else:
      dx_out = [self._output_javalib_jar]

    output = self.build(dx_out, 'dx',
                        implicit=[self._output_classes_jar],
                        variables=variables)

    if self._java_resource_dirs:
      jar_command = ''
      # See android/build/core/base_rules.mk, LOCAL_JAVA_RESOURCE_DIRS.
      excludes = ['.svn', '.java', 'package.html', 'overview.html', '.swp',
                  '.DS_Store', '~']
      # Exclude ARC specific files, too.
      excludes.extend(['OWNERS', 'README.txt'])
      staging_root = build_common.get_staging_root()
      for d in self._java_resource_dirs:
        # Resource directories that are generated via make_to_ninja point to
        # staging directories.
        resources = find_all_files(d, exclude=excludes,
                                   use_staging=not d.startswith(staging_root))
        for r in resources:
          rel_path = os.path.relpath(r, d)
          jar_command += ' -C %s %s' % (staging.as_staging(d), rel_path)
      assert jar_command
      output = self.build([self._output_javalib_jar], 'jar_update',
                          dx_out,
                          variables={'jar_command': jar_command})
    return output

  def _build_javalib_jar(self):
    if self._canned_jar_dir:
      return self.build(self._output_javalib_jar, 'cp',
                        os.path.join(self._canned_jar_dir, 'javalib.jar'))
    if self._is_static_library:
      return self.build(self._output_javalib_jar, 'cp',
                        self._output_classes_jar)

    return self._build_javalib_jar_from_classes_jar()

  def archive(self):
    """Builds JAR, dex code, and optional odex and classes jar."""
    classes = self._build_classes_jar()
    self._build_javalib_jar()
    if self._output_odex_file:
      self._build_odex_and_stripped_javalib(self._output_odex_file,
                                            self._output_jar,
                                            self._output_javalib_jar,
                                            install_jar=self._install_jar)
    return classes

  def install(self):
    """Installs the archive/output jar to its install location."""
    super(JarNinjaGenerator, self).install_to_root_dir(self._install_jar,
                                                       self._output_jar)
    if self._output_odex_file:
      super(JarNinjaGenerator, self).install_to_root_dir(
          JavaNinjaGenerator._change_extension(self._install_jar, '.odex',
                                               '.jar'),
          self._output_odex_file)
    return self


class ApkFromSdkNinjaGenerator(NinjaGenerator):
  """Builds an APK using the Android SDK directly."""

  def __init__(self, module_name, base_path=None, install_path=None,
               use_ndk=False, **kwargs):
    super(ApkFromSdkNinjaGenerator, self).__init__(
        module_name,
        ninja_name=module_name + '_apk',
        base_path=base_path,
        **kwargs)
    if install_path is None:
      install_path = \
          ApkFromSdkNinjaGenerator.get_install_path_for_module(module_name)
    self._install_path = install_path
    self._use_ndk = use_ndk

  @staticmethod
  def get_install_path_for_module(module_name):
    # Get the installation path, which will always be non-target specific
    # because even if there is NDK, we build all NDK targets.
    return os.path.join(build_common.get_build_path_for_apk(
        module_name), module_name + '.apk')

  @staticmethod
  def emit_common_rules(n):
    dbg = '' if OPTIONS.disable_debug_code() else '--debug'
    n.rule('build_using_sdk',
           ('python %s --build_path=$build_path --apk=$out %s ' +
            '--source_path=$source_path $args > $log 2>&1 || ' +
            '(cat $log; exit 1)') % ('src/build/build_using_sdk.py', dbg),
           description='build_using_sdk.py $out')

  def build_default_all_sources(self, implicit=None):
    files = self.find_all_contained_files(None, include_tests=True)
    build_path = os.path.dirname(self._install_path)
    build_script = os.path.join(build_common.get_arc_root(),
                                'src', 'build', 'build_using_sdk.py')
    implicit = as_list(implicit)
    implicit += map(staging.third_party_to_staging,
                    build_common.get_android_sdk_ndk_dependencies())
    implicit += [build_script]
    args = ''
    if self._use_ndk:
      args = '--use_ndk'

    variables = {
        'build_path': build_path,
        'log': os.path.join(build_path, 'build.log'),
        'source_path': staging.as_staging(self.get_base_path()),
        'args': args
    }
    return self.build([self._install_path], 'build_using_sdk', inputs=files,
                      variables=variables, implicit=implicit)

  @staticmethod
  def get_final_package_for_apk(apk_name):
    return build_common.get_build_path_for_apk(
        apk_name, subpath=apk_name + '.apk')


class ApkNinjaGenerator(JavaNinjaGenerator):
  def __init__(self, module_name, base_path=None, source_subdirectories=None,
               install_path=None, canned_classes_apk=None, install_lazily=False,
               **kwargs):
    # Set the most common defaults for APKs.
    if source_subdirectories is None:
      source_subdirectories = ['src']

    if os.path.exists(staging.as_staging(os.path.join(base_path or '', 'res'))):
      resource_subdirectories = 'res'
    else:
      resource_subdirectories = None

    super(ApkNinjaGenerator, self).__init__(
        module_name,
        ninja_name=module_name + '_apk',
        base_path=base_path,
        source_subdirectories=source_subdirectories,
        resource_subdirectories=resource_subdirectories,
        **kwargs)

    self._install_path = install_path

    self._aapt_input_path = self._get_build_path(subpath='apk')
    self._output_classes_dex = os.path.join(self._aapt_input_path,
                                            'classes.dex')
    self._dex_preopt = install_path is not None

    self._aligned_apk_archive = self._get_build_path(
        subpath='package.apk.aligned')
    self._unaligned_apk_archive = self._get_build_path(
        subpath='package.apk.unaligned')
    if self._dex_preopt:
      self._output_odex_file = self._get_build_path(
          subpath='package.odex', is_target=True)

    self._canned_classes_apk = canned_classes_apk
    self._install_lazily = install_lazily

  @staticmethod
  def emit_common_rules(n):
    n.rule('zipalign',
           toolchain.get_tool('java', 'zipalign') + ' -f 4 $in $out',
           description='zipalign $out')

  def _get_build_path(self, subpath=None, is_target=False):
    return build_common.get_build_path_for_apk(
        self._module_name, subpath=subpath, is_target=is_target)

  @staticmethod
  def get_final_package_for_apk(module_name, dex_preopt=False):
    # Note that the dex-preopt'ed package.apk without classes.dex is
    # technically not target specific, but upstream Android build
    # system puts it under target, so we follow their example.
    return build_common.get_build_path_for_apk(
        module_name,
        is_target=dex_preopt,
        subpath='package.apk')

  def get_final_package(self):
    return ApkNinjaGenerator.get_final_package_for_apk(self._module_name,
                                                       self._dex_preopt)

  def add_resource_paths(self, paths):
    self._resource_paths += paths

  def _build_classes_dex_from_class_files(self, outputs):
    stamp_files = self._extract_jar_contents()
    variables = dict(in_path=self._get_compiled_class_path())
    return self.build(outputs, 'dx',
                      implicit=self._javac_stamp_files + stamp_files,
                      variables=variables)

  def add_apk_deps(self, *deps, **kwargs):
    """Indicate that the generated APK depends on the given APKs.

    This is primarily for use in building Test APKs.  Calling this
    makes every class in every APK in |deps| accessible to every class
    in the APK we are generating.  We implement this by augmenting the
    generated APK's classpath and creating implicit dependencies on
    all the dependent APKs.
    """
    dex_preopt = kwargs.get('dex_preopt', False)
    self._javac_classpath_dirs.extend(
        [JavaNinjaGenerator.get_compiled_class_path_for_module(m)
         for m in deps])
    self._implicit.extend(
        [ApkNinjaGenerator.get_final_package_for_apk(m, dex_preopt=dex_preopt)
         for m in deps])

  def _get_minimal_bootclasspath(self):
    """Provides a minimal bootclasspath for building these java files.

    The bootclasspath defines the core library and other required class
    files that every Java file will have access to.  Without providing
    a -bootclasspath option, the Java compiler would instead consult its
    built-in core libraries, whereas Android uses a separate Apache
    core library (as well as API frameworks, etc).  We prevent APKs from
    accessing jars they should not need (such as service related jars)
    by not including any jars that appear after framework2 in the
    bootclasspath list.

    Currently APKs are being compiled using our custom built jars which
    contain many internal classes. In the future we could create a jar
    that contains only stubs for a stricter subset of classes that should
    be accessible to APKs (like the Android SDK does with android.jar).
    """
    return _truncate_list_at(
        _BootclasspathComputer.get_classes(),
        build_common.get_build_path_for_jar('framework2',
                                            subpath='classes.jar'),
        is_inclusive=True)

  def _build_and_add_all_generated_sources(self, implicit=None):
    super(ApkNinjaGenerator, self)._build_and_add_all_generated_sources()
    if implicit is None:
      implicit = []
    self.build_and_add_resources(implicit=implicit)

  def _build_zipalign(self, aligned_apk, unaligned_apk):
    return self.build(aligned_apk, 'zipalign', unaligned_apk)

  def _build_classes_apk(self):
    """Builds the .apk file from the .class files, and optionally installs it
    to the target root/app subdirectory."""
    self._build_classes_dex_from_class_files(outputs=[self._output_classes_dex])

    # Bundle up everything as an unsigned/unaligned .apk
    self._build_aapt(output_apk=self._unaligned_apk_archive,
                     implicit=[self._output_classes_dex],
                     input_path=self._aapt_input_path)

    # Optimize the .apk layout
    self._build_zipalign(self._aligned_apk_archive, self._unaligned_apk_archive)
    return self

  # TODO(crbug.com/394394): We could make the build system detect secondary dex
  # files automatically, but since L-release will support multiple dex at
  # framework level, we should refactor the way pre-dexopt is done here when we
  # uprev to L.
  def package(self, secondary_dex_files=None, multidex_output_dir=None):
    if not self._canned_classes_apk:
      self._build_classes_apk()
    else:
      self.build(self._aligned_apk_archive, 'cp', self._canned_classes_apk)

    # We differ from upstream in the apk packaging names.  Upstream
    # moves package.apk.aligned to package.apk and then optionally
    # modifies it in place if pre-dexopt'ing is done.  We leave each
    # build artifact in place to improve debugging (and because Ninja
    # will not allow doing modifications in place).
    if self._dex_preopt:
      self._build_odex_and_stripped_javalib(
          self._output_odex_file,
          self.get_final_package(),
          self._aligned_apk_archive,
          secondary_dex_files=secondary_dex_files,
          multidex_output_dir=multidex_output_dir)
    else:
      self.build(self.get_final_package(), 'cp',
                 self._aligned_apk_archive)
    return self.get_final_package()

  def install(self):
    install_to = os.path.join(self._install_path, self._module_name + '.apk')
    super(ApkNinjaGenerator, self).install_to_root_dir(install_to,
                                                       self.get_final_package())
    if self._dex_preopt:
      super(ApkNinjaGenerator, self).install_to_root_dir(
          JavaNinjaGenerator._change_extension(install_to, '.odex', '.apk'),
          self._output_odex_file)

    if self._install_lazily:
      # To retrieve intent-filter and provider in bootstrap, copy
      # AndroidManifest.xml as <module name>.xml.
      manifest_path = staging.as_staging(
          os.path.join(self._base_path, 'AndroidManifest.xml'))
      install_manifest_path = os.path.join(self._install_path,
                                           '%s.xml' % self._module_name)
      super(ApkNinjaGenerator, self).install_to_root_dir(
          install_manifest_path, manifest_path)
    return self


class AtfNinjaGenerator(ApkNinjaGenerator):
  def __init__(self, module_name, **kwargs):
    super(AtfNinjaGenerator, self).__init__(module_name, **kwargs)
    self.add_built_jars_to_classpath('android.test.runner')

  @staticmethod
  def emit_common_rules(n):
    n.rule('unsign_apk',
           'cp $in $out && zip -q -d $out META-INF/*',
           description='unsign apk $out')

  def build_default_all_test_sources(self):
    return self.build_default_all_sources(include_tests=True)


class AaptNinjaGenerator(NinjaGenerator):
  """Implements a simple aapt package generator."""

  _resource_paths = []
  _assets_path = None

  def __init__(self, module_name, base_path, manifest, intermediates,
               install_path=None, **kwargs):
    super(AaptNinjaGenerator, self).__init__(
        module_name, base_path=base_path, **kwargs)
    self._manifest = manifest
    self._intermediates = intermediates
    self._install_path = install_path

  def add_resource_paths(self, paths):
    self._resource_paths += paths

  def add_aapt_flag(self, value):
    self.add_flags('aaptflags', value)

  def get_resource_generated_path(self):
    return build_common.get_build_path_for_apk(self._module_name,
                                               subpath='R')

  def package(self, **kwargs):
    basename_apk = self._module_name + '.apk'
    resource_generated = self.get_resource_generated_path()

    extra_flags = ''
    implicit_depends = []

    if not self._resource_paths:
      path = os.path.join(self._base_path, 'res')
      if os.path.exists(path):
        self._resource_paths = [path]
    self.add_notice_sources([os.path.join(p, 'file')
                             for p in self._resource_paths])
    for path in self._resource_paths:
      extra_flags += ' -S ' + path
      implicit_depends += find_all_files(
          [path], use_staging=False, include_tests=True)

    if not self._assets_path:
      path = os.path.join(self._base_path, 'assets')
      if os.path.exists(path):
        self._assets_path = path
    if self._assets_path:
      extra_flags += ' -A ' + self._assets_path
      implicit_depends += find_all_files(
          [self._assets_path], use_staging=False, include_tests=True)

    apk_path = os.path.join(resource_generated, basename_apk)
    apk_path_unaligned = apk_path + '.unaligned'
    # -z requires localization.
    # -u forces aapt to update apk file, otherwise the file may not be touched.
    extra_flags += ' -z -u -F ' + apk_path_unaligned
    extra_flags += ' -J ' + resource_generated

    result_files = map(lambda x: os.path.join(resource_generated, x),
                       self._intermediates)
    result_files += [apk_path_unaligned]

    manifest = staging.as_staging(os.path.join(self._base_path, self._manifest))
    implicit_depends.append(manifest)
    self.build(
        result_files, 'aapt_package', [],
        variables={'aaptflags': '$aaptflags ' + extra_flags,
                   'manifest': manifest,
                   'tmpfile': os.path.join(resource_generated, 'errors')},
        implicit=implicit_depends)

    # Align for faster mmap.
    self.build(apk_path, 'zipalign', apk_path_unaligned)

    if self._install_path is not None:
      relpath = os.path.join(self._install_path, basename_apk)
      self.install_to_root_dir(relpath, apk_path)
    return apk_path


class PythonTestNinjaGenerator(NinjaGenerator):
  """Implements a python unittest runner generator."""
  def __init__(self, module_name, **kwargs):
    super(PythonTestNinjaGenerator, self).__init__(module_name, **kwargs)

  @staticmethod
  def emit_common_rules(n):
    # Running the test this way is a little awkward in that we are not really
    # interested in searching for tests matching a pattern, but it does what we
    # want.
    n.rule('run_python_test',
           ('PYTHONPATH=third_party/tools/python_mock python -m '
            'unittest discover --verbose $test_path $test_name $top_path' +
            build_common.get_test_output_handler()),
           description='run_python_test $in')

  def run(self, top_path, unit_test_module, implicit_dependencies=None):
    """Runs a single test from a larger package.

    'top_path' identifies the path to the top or root of the package source
    code. 'unit_test_module' is the full path the unit test to run."""
    top_path = staging.as_staging(top_path)
    unit_test_module = staging.as_staging(unit_test_module)
    results_file = os.path.join(build_common.get_target_common_dir(),
                                'test_results',
                                self.get_module_name() + '.results')
    test_path, test_name = os.path.split(unit_test_module)
    return self.build(results_file, 'run_python_test',
                      inputs=[unit_test_module],
                      implicit=implicit_dependencies,
                      variables=dict(test_path=test_path, test_name=test_name,
                                     top_path=top_path))


def _generate_python_test_ninja(top_path, python_test):
  ninja_name = os.path.splitext(python_test)[0].replace('/', '_')
  n = PythonTestNinjaGenerator(ninja_name)
  implicit_dependencies = \
      build_common.find_python_dependencies(top_path, python_test)
  n.run(top_path, python_test, implicit_dependencies=implicit_dependencies)


def generate_python_test_ninjas_for_path(top_path):
  python_tests = build_common.find_all_files(top_path, suffixes='_test.py',
                                             include_tests=True)
  request_run_in_parallel(*[(_generate_python_test_ninja, top_path, python_test)
                          for python_test in python_tests])


def build_default(n, root, files, **kwargs):
  build_out = []
  for one_file in files:
    path = one_file
    if root is not None:
      path = os.path.join(root, one_file)
    if one_file.endswith('.c'):
      build_out += n.cc(path, **kwargs)
    elif one_file.endswith('.cc') or one_file.endswith('.cpp'):
      build_out += n.cxx(path, **kwargs)
    elif one_file.endswith('.S'):
      build_out += n.asm_with_preprocessing(path, **kwargs)
    elif one_file.endswith('.s'):
      build_out += n.asm(path, **kwargs)
    else:
      raise Exception('No default rule for file ' + one_file)
  return build_out


def get_optimization_cflags():
  # These flags come from $ANDROID/build/core/combo/TARGET_linux-x86.mk.
  # Removed -ffunction-sections for working around crbug.com/231034. Also
  # removed -finline-limit=300 to fix crbug.com/243405.
  #
  # We also removed -fno-inline-functions-called-once as this was not
  # giving any value for ARC. There were no performance/binary size
  # regressions by removing this flag.
  return ['-O2',
          '-finline-functions',
          '-funswitch-loops']


# TODO(crbug.com/177699): Remove ignore_dependency option (we never
# should ignore dependencies) as part of dynamically generating
# the regen rules.
def open_dependency(path, access, ignore_dependency=False):
  """Open a file that configure depends on to generate build rules.

  Any file that we depend on to generate rules needs to be listed as
  a dependency for rerunning configure.  Set ignore_dependency to
  true if there are a bunch of files that are being added as
  dependencies which we do not yet reflect in
  TopLevelNinjaGenerator._regen_{input,output}_dependencies.
  """
  if not ignore_dependency:
    if 'w' in access:
      RegenDependencyComputer.verify_is_output_dependency(path)
    else:
      RegenDependencyComputer.verify_is_input_dependency(path)
  return open(path, access)


def _compute_hash_fingerprint(input):
  return hashlib.sha256(input).hexdigest()[0:8]


# TODO(kmixter): This function is used far too much with
# ignore_dependency=True.  Every path passed here should technically be
# listed as a regen dependency of configure.py. Currently we are using
# this function to parse every single eventlogtag, aidl, and
# AndroidManifest.xml file for package paths to determine file names.
# In many cases these package names are just used for generated file
# paths which do not really need to match package paths.  Fix this.
def _extract_pattern_from_file(path, pattern, ignore_dependency=False):
  """Given a path to a file, and a pattern, extract the string matched by the
  pattern from the file. Useful to grab a little bit of data from a file
  without writing a custom parser for that file type."""
  with open_dependency(path, 'r', ignore_dependency) as f:
    try:
      return re.search(pattern, f.read()).groups(1)[0]
    except Exception as e:
      raise Exception('Error matching pattern in %s: "%s"' % (path, e))


def _truncate_list_at(my_list, my_terminator, is_inclusive=False):
  if my_terminator not in my_list:
    return my_list
  addend = 0
  if is_inclusive:
    addend = 1
  return my_list[:my_list.index(my_terminator) + addend]


def get_bootclasspath():
  return _BootclasspathComputer.get_string()
