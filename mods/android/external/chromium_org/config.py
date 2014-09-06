# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libwebviewchromium code."""

import os

import build_common
import make_to_ninja
import ninja_generator
import ninja_generator_runner

from build_options import OPTIONS

# A map which provides a relative path for a directory that contains template
# file to generate Java source files for each chromium component.
_GYP_TEMPLATE_PATH_MAP = {
    'base': 'base/android/java/src/org/chromium/base',
    'content': 'content/public/android/java/src/org/chromium/content',
    'net': 'net/android/java',
    'ui': 'ui/android/java'}


def _update_cflags(vars, flags_to_add, flags_to_remove):
  for cflag in flags_to_add:
    vars.get_cflags().append(cflag)
  for cflag in flags_to_remove:
    if cflag in vars.get_cflags():
      vars.get_cflags().remove(cflag)


def _filter_cflags_for_chromium_org(vars):
  # Remove -Os because NaCl's gcc does not support it.  Add it back for
  # bare metal targets below.
  append_cflags = []
  strip_cflags = ['-fuse-ld=gold', '-march=pentium4', '-Os',
                  '-finline-limit=64']
  # Workaround for https://code.google.com/p/nativeclient/issues/detail?id=3205
  webcore_derived = 'third_party_WebKit_Source_core_webcore_derived_gyp'
  if vars.get_module_name() == webcore_derived and OPTIONS.is_arm():
    if '-O0' in vars.get_cflags():
      strip_cflags.append('-O0')
      append_cflags.append('-O2')
  # TODO(crbug.com/346783): Remove this once we NaCl'ize PageAllocator.cpp.
  # It is only necessary for NaCl, but we do this for linux as well
  # to minimize platform differences.
  append_cflags.append('-DMEMORY_TOOL_REPLACES_ALLOCATOR')
  _update_cflags(vars, append_cflags, strip_cflags)
  # -finline-limit=32 experimentally provides the smallest binary across
  # the li,ni,nx targets.  Also specify -finline-functions so all functions
  # are candidates for inlining.
  size_opts = ['-finline-limit=32', '-finline-functions']
  if OPTIONS.is_bare_metal_build():
    size_opts += ['-Os']
  else:
    # These options are used for -Os, so we set them manually because -Os does
    # not work in NaCl gcc.
    # http://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html
    size_opts += ['-fno-align-functions', '-fno-align-jumps',
                  '-fno-align-loops', '-fno-align-labels',
                  '-fno-reorder-blocks', '-fno-prefetch-loop-arrays',
                  '-fno-reorder-blocks-and-partition',
                  '-fno-tree-vect-loop-version']
  vars.get_cflags()[:] = vars.get_cflags() + size_opts
  # dlopen fails for the following undefined reference without -mthumb
  # _ZN7WebCore26feLightingConstantsForNeonEv
  # TODO(crbug.com/358333): Investigate if this is actually needed.
  if OPTIONS.is_arm():
    vars.get_cflags().append('-mthumb')


def _filter_ldflags_for_libwebviewchromium(vars):
  if OPTIONS.is_bare_metal_build() or OPTIONS.is_nacl_build():
    # We need to pass in --no-keep-memory or ld runs out of memory linking.
    vars.get_ldflags().append('-Wl,--no-keep-memory')
  # --no-undefined allows undefined symbols to be present in the linked .so
  # without errors, which is what we want so they are resolved at runtime.
  vars.get_ldflags().remove('-Wl,--no-undefined')


def _filter_deps_for_libwebviewchromium(vars, skip):
  for s in skip:
    vars.get_static_deps().remove(s)
  vars.get_shared_deps().remove('libOpenSLES')


def _filter_sources_for_chromium_org(vars):
  # Strip out protobuf python generators.  These are canned in GYP along with
  # their header output.
  source_pattern_blacklist = ['_pb2.py', 'rule_trigger']
  sources = vars.get_sources()
  for pattern in source_pattern_blacklist:
    sources[:] = [s for s in sources if pattern not in s]


def _filter_params_for_v8(vars):
  # Switch V8 to always emit ARM code and use simulator to run that on
  # x86 NaCl.
  # Also disable snapshots as they are not working in ARC yet.
  if '-DV8_TARGET_ARCH_IA32' in vars.get_cflags() and OPTIONS.is_nacl_build():
    vars.get_cflags().remove('-DV8_TARGET_ARCH_IA32')
    vars.get_cflags().append('-DV8_TARGET_ARCH_ARM')
    vars.get_cflags().append('-D__ARM_ARCH_7__')
  sources = vars.get_sources()
  new_sources = []
  v8_src = 'android/external/chromium_org/v8/src/'
  for path in sources:
    if path.startswith(v8_src + 'ia32/') and OPTIONS.is_nacl_build():
      path = v8_src + 'arm/' + os.path.basename(path).replace('ia32', 'arm')
    if path.endswith('/snapshot.cc'):
      path = 'android/external/chromium_org/v8/src/snapshot-empty.cc'
    new_sources.append(path)
  if not OPTIONS.is_arm() and OPTIONS.is_nacl_build():
    new_sources.append(v8_src + 'arm/constants-arm.cc')
    new_sources.append(v8_src + 'arm/simulator-arm.cc')
  vars.get_sources()[:] = new_sources


def _get_chromium_modules_to_skip(vars):
  skip = [
      # Sandbox libraries are not used, and require extra mods.
      'sandbox_sandbox_services_gyp',
      'sandbox_seccomp_bpf_gyp',
      # We are linking against Android's static openssl libs already, so
      # allow libwebviewchromium to link against that instead of building
      # another copy of openssl.
      'third_party_openssl_openssl_gyp']
  if OPTIONS.is_x86():
    skip.extend([
        # These are x86 specific asm builds which are optional.
        'media_media_asm_gyp',
        'media_media_mmx_gyp',
        'media_media_sse_gyp',
        'media_media_sse2_gyp'])
  return skip


def _get_path_components_following_mark(path, mark):
  """Splits |path| and return a path components list that follow |mark|.

  For instance, when |path| is '/foo/mark/bar/baz' and |mark| is 'mark', it
  returns ['bar', 'baz'].
  """
  paths = path.split('/')
  return paths[paths.index(mark) + 1:]


def _fix_gen_source_path(path):
  """Fixes a generated source path that make_to_ninja can not expand correctly.

  |path| is something like '/<somewhere>/arc/out/target/common/make_to_ninja/
  out/target/product/generic_x86/obj/GYP/shared_intermediates/templates/org/
  chromium/base/ActivityState.java'. This strips a long full path prefix before
  'GYP/...', and make it replaced under the build dir as e.g., 'out/target/
  nacl_x86_64/obj/GYP/shared_intermediates/templates/org/chromium/base/
  ActivityState.java'.
  """
  return os.path.join(build_common.get_build_dir(), 'obj/GYP',
                      *_get_path_components_following_mark(path, 'GYP'))


def _get_template_path(base_path, path):
  """Provides a template file path for a Java source file.

  Some Java source files are generated from template files, and the place for
  template files are different and depend on chromium components. This function
  converts |path| for a generated Java source file to a template file path.
  For instance, when |path| is ['net', 'foo', 'bar.baz'], it returns
  'ui/android/java/net/bar.template' by using _GYP_TEMPLATE_PATH_MAP for the
  'net' components.
  For real Android build, Android.mk includes a bunch of .mk files to provide
  them. But make_to_ninja does not support 'LOCAL_MODULE_CLASS := GYP' used in
  .mk files.

  """
  chromium_path = _get_path_components_following_mark(path, 'chromium')
  template_path = _GYP_TEMPLATE_PATH_MAP[chromium_path[0]]
  name = os.path.splitext(os.path.join(*chromium_path[1:]))[0] + '.template'
  return os.path.join(base_path, '..', template_path, name)


def _filter_java_library(vars):
  module_name = vars.get_module_name()
  if module_name == 'android_webview_java':
    # Building parts of chromium is special and make_to_ninja can not handle
    # path expansion on LOCAL_GENERATED_SOURCES correctly. |sources| contains
    # files that are listed in LOCAL_GENERATED_SOURCES, and following code
    # replaces them with right places.
    sources = vars.get_generated_sources()
    sources[:] = [_fix_gen_source_path(x) for x in sources]

    # Generate a custom NinjaGenerator to generate Java source files from
    # template files.  This rule is based on target .mk files in
    # android/external/chromium_org/base/.
    # TODO(crbug.com/394654): Remove a manually converted NinjaGenerator once
    # make_to_ninja supports 'LOCAL_MODULE_CLASS := GYP' modules.
    n = ninja_generator.NinjaGenerator(module_name + '_gyp')
    n.rule('gyp_gcc_preprocess',
           'mkdir -p $out_dir && '
           'cd $work_dir && '
           'python ../build/android/gyp/gcc_preprocess.py '
           '--include-path=.. --output=$real_out --template=$in',
           description='gyp/gcc_preprocess.py --include-path=.. --output=$out '
                       '--template=$in')
    base_path = vars.get_path()
    for source in sources:
      template = _get_template_path(base_path, source)
      out_dir = os.path.dirname(source)
      work_dir = os.path.join(
          base_path, '..',
          _get_path_components_following_mark(source, 'chromium')[0])
      variables = {
          'out_dir': out_dir,
          'work_dir': work_dir,
          'real_out': os.path.realpath(source)}
      n.build(source, 'gyp_gcc_preprocess',
              inputs=os.path.realpath(template), variables=variables)
    return True
  return False


def _filter_target_modules(vars):
    skip = _get_chromium_modules_to_skip(vars)
    module_name = vars.get_module_name()
    if module_name in skip:
      return False
    if module_name == 'libwebviewchromium':
      _filter_deps_for_libwebviewchromium(vars, skip)
      _filter_ldflags_for_libwebviewchromium(vars)
    if module_name.startswith('v8_tools_gyp_'):
      _filter_params_for_v8(vars)
    if module_name == 'third_party_harfbuzz_ng_harfbuzz_ng_gyp':
      build_common.filter_params_for_harfbuzz(vars)
    _filter_cflags_for_chromium_org(vars)
    _filter_sources_for_chromium_org(vars)
    return True


# This is the ninja that generates libwebviewchromium.
def _generate_chromium_org_ninja():
  def _filter(vars):
    if vars.is_host():
      return False

    if vars.is_java_library():
      return _filter_java_library(vars)

    assert vars.is_target()
    return _filter_target_modules(vars)

  make_to_ninja.MakefileNinjaTranslator(
      'android/external/chromium_org').generate(_filter)


def _generate_webview_ninja():
  def _filter(vars):
    # TODO(crbug.com/390856): Build Java libraries from source.
    if vars.is_java_library():
      return False
    # This is a simple APK that loads a webview, not needed for ARC.
    skip = ['WebViewShell']
    if vars.get_module_name() in skip:
      return False
    return True

  make_to_ninja.MakefileNinjaTranslator(
      'android/frameworks/webview').generate(_filter)


def generate_ninjas():
  ninja_generator_runner.request_run_in_parallel(
      _generate_chromium_org_ninja,
      _generate_webview_ninja)
