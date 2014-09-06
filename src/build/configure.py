#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ast
import collections
import distutils.spawn
import os
import pipes
import shutil
import subprocess
import sys

import build_common
import config_loader
import download_cts_files
import download_sdk_and_ndk
import open_source
import staging
import sync_adb
import sync_nacl_sdk
import toolchain

from build_options import OPTIONS
import make_to_ninja
import ninja_generator
import ninja_generator_runner


def _set_up_git_hooks():
  # These git hooks do not make sense for the open source repo because they:
  # 1) lint the source, but that was already done when committed internally,
  #    and we will run 'ninja all' as a test step before committing to open
  #    source.
  # 2) add fields to the commit message for the internal dev workflow.
  if open_source.is_open_source_repo():
    return
  script_dir = os.path.dirname(__file__)
  hooks = {
      'pre-push': os.path.join(script_dir, 'git_pre_push.py'),
      'prepare-commit-msg': os.path.join(script_dir, 'git_prepare_commit.py'),
      'commit-msg': staging.as_staging('gerrit/commit-msg')}
  obsolete_hooks = ['pre-commit']  # Replaced by pre-push hook.

  git_hooks_dir = os.path.join(build_common.get_arc_root(), '.git', 'hooks')
  for git_hook, source_path in hooks.iteritems():
    symlink_path = os.path.join(git_hooks_dir, git_hook)
    build_common.create_link(symlink_path, source_path, overwrite=True)

  for git_hook in obsolete_hooks:
    symlink_path = os.path.join(git_hooks_dir, git_hook)
    if os.path.lexists(symlink_path):
      os.unlink(symlink_path)


def _check_java_version():
  # Stamp file should keep the last modified time of the java binary.
  java_path = distutils.spawn.find_executable(
      toolchain.get_tool('java', 'java'))
  stamp_file = build_common.StampFile(
      os.path.getmtime(java_path), build_common.get_java_revision_file())
  if stamp_file.is_up_to_date():
    return

  p = subprocess.Popen([toolchain.get_tool('java', 'java'), '-version'],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  want_version = '1.6.'
  java_version = p.communicate()[0]
  if want_version not in java_version:
    print '\nWARNING: You are not using the supported Java SE 1.6.'
    print 'See docs/getting-java.md\n'
  else:
    stamp_file.update()


def _cleanup_orphaned_pyc_files():
  # Watch out for .pyc files without a corresponding .py file
  for base_path in ('src/', 'mods/'):
    for root, dirs, files in os.walk(base_path):
      for name in files:
        fullpath = os.path.join(root, name)
        base, ext = os.path.splitext(fullpath)
        if ext == '.pyc' and not os.path.exists(base + '.py'):
          print ('\nWARNING: %s appears to be a compiled python file without '
                 'any associated python code. It has been removed.') % fullpath
          os.unlink(fullpath)


def _gclient_sync_third_party():
  gclient_filename = 'third_party/.gclient'

  # For whatever reason gclient wants to take revisions from the command line
  # and does not read them from the .gclient file -- they used to be part of the
  # url. To work around this, we look for a new revision key for each dictionary
  # in the .gclient solution array, and use that to pass the revision
  # information on the command line.
  # TODO(lpique): Modify gclient to have it look for 'revision' in the .gclient
  # file itself, which will make this block of code unnecessary.
  with open(gclient_filename) as f:
    # Read the gclient file ourselves to extract some extra information from it
    gclient_content = f.read()
    # Make sure it appears to have an expected beginning, so we can quickly
    # parse it.
    assert gclient_content.startswith('solutions = [')
    # Use ast.literal_eval on the array, which works to evaluate simple python
    # constants. Using the built-in eval is potentially unsafe as it can execute
    # arbitrary code.
    # We start with the first array bracket, ignoring anything before it.
    gclient_contents = ast.literal_eval(
        gclient_content[gclient_content.find('['):])

  with open(gclient_filename, 'r') as f:
    stamp_file = build_common.StampFile(
        gclient_content, build_common.get_thirdparty_gclient_revision_file())
  if stamp_file.is_up_to_date():
    return

  cmd = ['gclient', 'sync', '--gclientfile', os.path.basename(gclient_filename)]

  # TODO(lpique): Modify gclient to have it look for 'revision' in the .gclient
  # file itself, which will make this block of code unnecessary.
  for entry in gclient_contents:
    if 'name' in entry and 'revision' in entry:
      cmd.extend(['--revision', pipes.quote('%(name)s@%(revision)s' % entry)])

  try:
    subprocess.check_output(cmd, cwd=os.path.dirname(gclient_filename))
    stamp_file.update()
  except subprocess.CalledProcessError as e:
    sys.stderr.write(e.output)
    sys.exit('Error running "%s"' % ' '.join(cmd))


def _ensure_downloads_up_to_date():
  # Always sync NaCl SDK.
  verbosity_option = ['-v'] if OPTIONS.verbose() else []
  if sync_nacl_sdk.main(verbosity_option):
    sys.exit(1)

  if download_sdk_and_ndk.check_and_perform_updates():
    sys.exit(1)

  if download_cts_files.check_and_perform_updates():
    sys.exit(1)


def _configure_build_options():
  if OPTIONS.parse(sys.argv[1:]):
    print 'Args error'
    return False

  # Write out the configure file early so all other scripts can use
  # the options passed into configure. (e.g., sync_chrome).
  OPTIONS.write_configure_file()

  # Target directory is replaced. If an old directory, out/target/<target>,
  # exists, move it to the new place, out/target/<target>_<opt>.
  old_path = os.path.join('out/target', OPTIONS.target())
  new_path = build_common.get_build_dir()
  if os.path.lexists(old_path):
    if os.path.isdir(old_path) and not os.path.islink(old_path):
      if os.path.exists(new_path):
        shutil.rmtree(old_path)
      else:
        shutil.move(old_path, new_path)
    else:
      os.remove(old_path)

  # Create an empty directory as a placeholder if necessary.
  build_common.makedirs_safely(new_path)

  # Create a symlink from new place to old place to keep as compatible as
  # possible.
  os.symlink(os.path.basename(new_path), old_path)

  # Write out the configure file to a target specific location, which can be
  # queried later to find out what the config for a target was.
  OPTIONS.write_configure_file(build_common.get_target_configure_options_file())

  OPTIONS.set_up_goma()
  return True


def _filter_excluded_libs(vars):
  excluded_libs = [
      'libandroid',          # Added as an archive to plugin
      'libandroid_runtime',  # Added as an archive to plugin
      'libaudioutils',       # Converted to an archive
      'libbinder',           # Added as an archive to plugin
      'libcamera_client',    # Added as an archive to plugin
      'libcamera_metadata',  # Added as an archive to plugin
      'libcutils',           # Added as an archive to plugin
      'libcorkscrew',        # Added as an archive to plugin
      'libcrypto',           # Added as an archive to plugin
      'libcrypto_static',    # Added as an archive to plugin
      'libdl',               # Provided in Bionic replacement
      'libdvm',              # Added as an archive to plugin
      'libEGL',              # Added as an archive to plugin
      'libeffects',          # Added as an archive to plugin
      'libemoji',            # Added as an archive to plugin
      'libETC1',             # Added as an archive to plugin
      'libexpat',            # Added as an archive to plugin
      'libexpat_static',     # Added as an archive to plugin
      'libGLESv1_CM',        # Added as an archive to plugin
      'libGLESv2',           # Not built
      'libgui',              # Converted to an archive
      'libhardware',         # Added as an archive to plugin
      'libharfbuzz_ng',      # Added as an archive to plugin
      'libhwui',             # Added as an archive to plugin (when enabled)
      'libicui18n',          # Added as an archive to plugin
      'libicuuc',            # Added as an archive to plugin
      'libinput',            # Added as an archive to plugin
      'libjpeg',             # Added as an archive to plugin (as libjpeg_static)
      'liblog',              # Part of libcommon
      'libmedia',            # Converted to an archive
      'libskia',             # Added as an archive to plugin
      'libsonivox',          # Added as an archive to plugin
      'libsqlite',           # Added as an archive to plugin
      'libssl',              # Added as an archive to plugin
      'libssl_static',       # Added as an archive to plugin
      'libstlport',          # Trying to avoid in favor of GLIBC
      'libsync',             # FD sync is not supported
      'libui',               # Added as an archive to plugin
      'libz']                # Added as an archive to plugin

  deps = vars.get_shared_deps()
  deps[:] = [x for x in deps if x not in excluded_libs]
  deps = vars.get_static_deps()
  deps[:] = [x for x in deps if x not in excluded_libs]
  deps = vars.get_whole_archive_deps()
  deps[:] = [x for x in deps if x not in excluded_libs]


def _filter_for_nacl_x86_64(vars):
  # This supresses the -m32 load flag for 64-bit NaCl builds.
  if '-m32' in vars.get_ldflags():
    vars.get_ldflags().remove('-m32')


def _filter_for_arm(vars):
  # third_party/android/build/core/combo/TARGET_linux-arm.mk adds
  # this gold-only option for ARM. TODO(http://crbug.com/239870)
  # This flag may appear multiple times.
  while '-Wl,--icf=safe' in vars.get_ldflags():
    vars.get_ldflags().remove('-Wl,--icf=safe')


def _filter_libchromium_net(vars):
  # Handle libchromium_net. We have to convert libchromium_net to .a and
  # link it into shared libraries. Note that we cannot link it into the
  # plugin because of symbol conflicts with libchromium_base.a.
  assert 'libchromium_net' not in vars.get_static_deps()
  assert 'libchromium_net' not in vars.get_whole_archive_deps()
  deps = vars.get_shared_deps()
  if 'libchromium_net' in deps:
    deps.remove('libchromium_net')
    for lib in ['dmg_fp', 'libchromium_net', 'libevent', 'modp_b64']:
      vars.get_static_deps().append(lib)


def _filter_for_when_not_arm(vars):
  # Sources sometimes are explicitly listed with a .arm variant.  Use the
  # non-arm version instead.
  for source in vars.get_sources():
    base, ext = os.path.splitext(source)
    if ext == '.arm':
      vars.get_sources().remove(source)
      vars.get_sources().append(base)


def _filter_all_make_to_ninja(vars):
  # All the following filters are only for the target.
  if vars.is_host():
    return True
  if vars.is_java_library() and open_source.is_open_source_repo():
    # We do not yet build all of the Java prerequisites in the open source
    # repository.
    return False
  if vars.is_c_library() or vars.is_executable():
    _filter_excluded_libs(vars)
    _filter_libchromium_net(vars)

    if OPTIONS.is_nacl_x86_64():
      _filter_for_nacl_x86_64(vars)

    if OPTIONS.is_arm():
      _filter_for_arm(vars)
    else:
      _filter_for_when_not_arm(vars)

  return True


def _set_up_generate_ninja():
  # Create generated_ninja directory if necessary.
  ninja_dir = build_common.get_generated_ninja_dir()
  if not os.path.exists(ninja_dir):
    os.makedirs(ninja_dir)

  # Set up global implicit dependency specified by the option.
  deps = toolchain.get_tool(OPTIONS.target(), 'deps')
  ninja_generator.NinjaGenerator.add_global_implicit_dependency(deps)

  # Set up default resource path.
  framework_resources_base_path = (
      build_common.get_build_path_for_apk('framework-res', subpath='R'))
  ninja_generator.JavaNinjaGenerator.add_default_resource_include(
      os.path.join(framework_resources_base_path, 'framework-res.apk'))

  # Set up global filter for makefile to ninja translator.
  make_to_ninja.MakefileNinjaTranslator.add_global_filter(
      _filter_all_make_to_ninja)
  make_to_ninja.prepare_make_to_ninja()


def _generate_independent_ninjas():
  timer = build_common.SimpleTimer()

  # Invoke an unordered set of ninja-generators distributed across config
  # modules by name, and if that generator is marked for it.
  timer.start('Generating independent generate_ninjas', True)
  task_list = list(config_loader.find_name('generate_ninjas'))
  if OPTIONS.run_tests():
    task_list.extend(config_loader.find_name('generate_test_ninjas'))
  ninja_list = ninja_generator_runner.run_in_parallel(task_list,
                                                      OPTIONS.configure_jobs())
  timer.done()

  return ninja_list


def _generate_shared_lib_depending_ninjas(ninja_list):
  timer = build_common.SimpleTimer()

  timer.start('Generating plugin and packaging ninjas', OPTIONS.verbose())
  # We must generate plugin/nexe ninjas after make->ninja lazy generation
  # so that we have the full list of shared libraries to pass to
  # the load test.
  # These modules depend on shared libraries generated in the previous phase.
  installed_shared_libs = (
      ninja_generator.NinjaGenerator.get_installed_shared_libs(ninja_list[:]))
  ninja_generators = list(
      config_loader.find_name('generate_shared_lib_depending_ninjas'))
  task_list = [(f, installed_shared_libs) for f in ninja_generators]

  if OPTIONS.run_tests():
    test_ninja_generators = list(
        config_loader.find_name('generate_shared_lib_depending_test_ninjas'))
    task_list.extend([(f, installed_shared_libs)
                     for f in test_ninja_generators])

  result = ninja_generator_runner.run_in_parallel(task_list,
                                                  OPTIONS.configure_jobs())
  timer.done()
  return result


def _generate_dependent_ninjas(ninja_list):
  """Generate the stage of ninjas coming after all executables."""
  timer = build_common.SimpleTimer()

  timer.start('Generating dependent ninjas', OPTIONS.verbose())

  root_dir_install_all_targets = []
  for n in ninja_list:
    root_dir_install_all_targets.extend(build_common.get_android_fs_path(p) for
                                        p in n._root_dir_install_targets)
  dependent_ninjas = ninja_generator_runner.run_in_parallel(
      [(job, root_dir_install_all_targets) for job in
       config_loader.find_name('generate_binaries_depending_ninjas')],
      OPTIONS.configure_jobs())

  notice_ninja = ninja_generator.NoticeNinjaGenerator('notices')
  notice_ninja.build_notices(ninja_list + dependent_ninjas)
  dependent_ninjas.append(notice_ninja)
  return dependent_ninjas


def _generate_top_level_ninja(ninja_list):
  """Generate build.ninja.  This must be the last generated ninja."""
  top_ninja = ninja_generator.TopLevelNinjaGenerator('build.ninja')
  top_ninja.emit_subninja_rules(ninja_list)
  top_ninja.emit_target_groups_rules(ninja_list + [top_ninja])
  return top_ninja


def _verify_ninja_generator_list(ninja_list):
  module_name_count_dict = collections.defaultdict(int)
  archive_ninja_list = []
  shared_ninja_list = []
  exec_ninja_list = []
  for ninja in ninja_list:
    # Use is_host() in the key as the accounting should be done separately
    # for the target and the host.
    key = (ninja.get_module_name(), ninja.is_host())
    module_name_count_dict[key] += 1
    if isinstance(ninja, ninja_generator.ArchiveNinjaGenerator):
      archive_ninja_list.append(ninja)
    if isinstance(ninja, ninja_generator.SharedObjectNinjaGenerator):
      shared_ninja_list.append(ninja)
    if (isinstance(ninja, ninja_generator.ExecNinjaGenerator) and
        # Do not check the used count of tests.
        not isinstance(ninja, ninja_generator.TestNinjaGenerator)):
      exec_ninja_list.append(ninja)

  # Make sure there is no duplicated ninja modules.
  duplicated_module_list = [
      item for item in module_name_count_dict.iteritems() if item[1] > 1]
  if duplicated_module_list:
    errors = []
    for (module_name, is_host), count in duplicated_module_list:
      host_or_target = ('host' if is_host else 'target')
      error = '%s for %s: %d' % (module_name, host_or_target, count)
      errors.append(error)
    raise Exception(
        'Ninja generated multiple times: ' + ', '.join(errors))

  # Make sure for each modules, the expected usage count and actual reference
  # count is same.  The open source repository builds a subset of binaries so
  # we do not check its numbers.
  if not open_source.is_open_source_repo():
    ninja_generator.ArchiveNinjaGenerator.verify_usage_counts(
        archive_ninja_list, shared_ninja_list, exec_ninja_list)


def _set_up_chromium_org_submodules():
  # android/external/chromium_org contains these required submodules.  It is not
  # posible to have submodules within a submodule path (i.e., chromium_org)
  # using git submodules.  This is the list of subdirectories relative to
  # chromium_org that we need to symlink to the appropriate submodules.
  submodules = [
      'sdch/open-vcdiff',
      'testing/gtest',
      'third_party/WebKit',
      'third_party/angle_dx11',
      ('third_party/eyesfree/src/android/java/'
       'src/com/googlecode/eyesfree/braille'),
      'third_party/freetype',
      'third_party/icu',
      'third_party/leveldatabase/src',
      'third_party/libjingle/source/talk',
      'third_party/libphonenumber/src/phonenumbers',
      'third_party/libphonenumber/src/resources',
      'third_party/mesa/src',
      'third_party/openssl',
      'third_party/opus/src',
      'third_party/ots',
      'third_party/skia/gyp',
      'third_party/skia/include',
      'third_party/skia/src',
      'third_party/smhasher/src',
      'third_party/yasm/source/patched-yasm',
      'v8']

  for s in submodules:
    symlink = os.path.join('third_party/android/external/chromium_org', s)
    # As an example, this maps 'sdch/open-vcdiff' to
    # 'android/external/chromium_org__sdch_open-vcdiff', which is the true
    # location of the submodule checkout.
    source = 'third_party/android/external/chromium_org__' + s.replace('/', '_')
    if not os.path.exists(source):
      print 'ERROR: path "%s" does not exist.' % source
      print 'ERROR: Did you forget to run git submodules update --init?'
      sys.exit(1)
    build_common.create_link(symlink, source, overwrite=True)


def _generate_ninjas():
  _set_up_generate_ninja()
  ninja_list = []
  ninja_list.extend(_generate_independent_ninjas())
  ninja_list.extend(
      _generate_shared_lib_depending_ninjas(ninja_list))
  ninja_list.extend(_generate_dependent_ninjas(ninja_list))
  ninja_list.append(_generate_top_level_ninja(ninja_list))

  # Run verification before emitting to files.
  _verify_ninja_generator_list(ninja_list)

  # Emit each ninja script to a file.
  timer = build_common.SimpleTimer()
  timer.start('Emitting ninja scripts', OPTIONS.verbose())
  for ninja in ninja_list:
    ninja.emit()
  timer.done()


def main():
  # Disable line buffering
  sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

  if not _configure_build_options():
    return -1

  _ensure_downloads_up_to_date()

  if not open_source.is_open_source_repo():
    import sync_chrome
    sync_chrome.run()

  adb_target = 'linux-arm' if OPTIONS.is_arm() else 'linux-x86_64'
  sync_adb.run(adb_target)

  if (build_common.has_internal_checkout() and
      OPTIONS.internal_apks_source() != 'canned'):
    # Sync arc-int repo and and its sub-repo.
    subprocess.check_call('src/build/sync_arc_int.py')

  _gclient_sync_third_party()
  _check_java_version()
  _cleanup_orphaned_pyc_files()

  _set_up_git_hooks()

  _set_up_chromium_org_submodules()

  # Make sure the staging directory is up to date whenever configure
  # runs to make it easy to generate rules by scanning directories.
  staging.create_staging()

  _generate_ninjas()

  return 0


if __name__ == '__main__':
  sys.exit(main())
