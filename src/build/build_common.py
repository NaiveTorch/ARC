# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Code shared between configure.py and generate_chrome_launch_script.py

import atexit
import errno
import fnmatch
import json
import logging
import modulefinder
import os
import pipes
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib2

from build_options import OPTIONS
from util import platform_util

OUT_DIR = 'out'
# When running Python unittest set up by PythonTestNinjaGenerator, this file
# is loaded as out/staging/src/build/build_common.py. Use os.path.realpath
# so that get_arc_root() always returns the real ARC root directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
_ARC_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

# Libraries that are used for checking static initializers.
CHECKED_LIBRARIES = ['arc_nacl_x86_64.nexe', 'libposix_translation.so']

COMMON_EDITOR_TMP_FILE_PATTERNS = ['.*.swp', '*~', '.#*', '#*#']
COMMON_EDITOR_TMP_FILE_REG = re.compile(
    '|'.join('(?:' + fnmatch.translate(pattern) + ')'
             for pattern in COMMON_EDITOR_TMP_FILE_PATTERNS))
CHROME_USER_DATA_DIR_PREFIX = 'arc-test-profile-pepper'

_LAUNCH_CHROME_COMMAND_REG = re.compile(r'launch_chrome(\.py)?')

# These arguments to launch_chrome are only meant to be used by the integration
# test infrastructure, and might lead to confusing results if someone copies and
# pastes the command line we issue.
_LAUNCH_CHROME_ARGS_TO_FILTER = (
    # This option is added to isolate the execution of multiple tests and to
    # enable them to run in parallel. This is unnecessary when running a
    # single test manually.
    '--use-temporary-data-dirs',
    # This is added to avoid rebuilding the CRX for the test, which is
    # built in the prepare step of the integration tests. This needs to be
    # omitted when running a test manually with launch_chrome command.
    '--nocrxbuild')

# If test succeeds, $out will be written and there will be no terminal
# output. If the test fails, this shows the test output in the
# terminal and does exit 1. $out will not be written and $out.tmp will
# have the output when the test failed.
_TEST_OUTPUT_HANDLER = (' > $out.tmp 2>&1 && mv $out.tmp $out ' +
                        '|| (cat $out.tmp;%s exit 1)')


class SimpleTimer:
  def __init__(self):
    self._start_time = 0
    self._running = False
    self._show = False

  def start(self, msg, show=False):
    assert(not self._running)
    self._start_time = time.time()
    self._running = True
    self._show = show
    if self._show:
      sys.stdout.write(msg + '...')

  def done(self):
    assert(self._running)
    if self._show:
      total_time = time.time() - self._start_time
      sys.stdout.write('.. done! [%0.3fs]\n' % (total_time))
    self._running = False


class StampFile(object):
  def __init__(self, revision, stamp_file, force=False):
    self._revision = str(revision).strip()
    self._stamp_file = stamp_file
    self._force = force

  def is_up_to_date(self):
    """Returns True if stamp file says it is up to date."""
    logging.info('Considering stamp file: %s', self._stamp_file)

    # For force updating, the stamp should be always out of date.
    if self._force:
      logging.info('Always treating as out of date')
      return False

    if os.path.exists(self._stamp_file):
      with open(self._stamp_file, 'r') as f:
        # Ignore leading and trailing white spaces.
        stamp = f.read().strip()
    else:
      stamp = ''

    logging.info('Comparing current stamp \'%s\' to expected \'%s\'',
                 stamp, self._revision)
    return stamp == self._revision

  def update(self):
    """Updates the stamp file to the current revision."""
    with open(self._stamp_file, 'w') as f:
      f.write(self._revision + '\n')


def as_list(input):
  if input is None:
    return []
  if isinstance(input, list):
    return input
  return [input]


def as_dict(input):
  if input is None:
    return dict()
  if isinstance(input, dict):
    return input
  raise TypeError('Cannot convert to dictionary')


# TODO(crbug.com/366082): Move the following four functions to somewhere else.
def get_launch_chrome_command(options=[]):
  # Run launch_chrome script using /bin/sh so that the script can be executed
  # even if it is on the filesystem with noexec option (e.g. Chrome OS)
  return ['/bin/sh', 'launch_chrome'] + options


def parse_launch_chrome_command(args):
  if args[0] == 'xvfb-run':
    if '/bin/sh' in args:
      args = args[args.index('/bin/sh'):]
  if args[0] == '/bin/sh':
    args = args[1:]
  return args


def is_launch_chrome_command(argv):
  args = parse_launch_chrome_command(argv)
  return bool(_LAUNCH_CHROME_COMMAND_REG.match(
      os.path.basename(os.path.realpath(args[0]))))


def remove_leading_launch_chrome_args(argv):
  """Removes the leading args of launch chrome command except option args.

  Examples:
    ['/bin/sh', './launch_chrome', 'run', '-v'] => ['run', '-v']
    ['./launch_chrome', 'run', '--noninja'] => ['run', '--noninja']
  """
  assert(is_launch_chrome_command(argv))
  args = parse_launch_chrome_command(argv)
  return args[1:]


def log_subprocess_popen(args, bufsize=0, executable=None, stdin=None,
                         stdout=None, stderr=None, preexec_fn=None,
                         close_fds=False, shell=False, cwd=None, env=None,
                         universal_newlines=False, startupinfo=None,
                         creationflags=0):
  """Outputs the subprocess command line to the logging.info.

  The arguments of this function are the same as that of the Popen constructor.
  """
  safe_args = args
  unsafe_args = []
  if is_launch_chrome_command(args):
    safe_args = filter(lambda x: x not in _LAUNCH_CHROME_ARGS_TO_FILTER, args)
    unsafe_args = filter(lambda x: x in _LAUNCH_CHROME_ARGS_TO_FILTER, args)

  output_text = []

  # If cwd was specified, emulate it with a pushd
  if cwd:
    output_text.extend(['pushd', cwd, ';'])
  if env:
    output_text.extend('%s=%s' % item for item in env.iteritems())
  if executable:
    output_text.append(executable)
  output_text.extend(safe_args)
  # If cwd was specified, clean up with a popd
  if cwd:
    output_text.extend([';', 'popd'])

  logging.info('$ ' + pipes.quote(' '.join(output_text)))

  if unsafe_args:
    logging.info('NOTE: The following options were omitted in the command '
                 'line above to make it suitable for debugging use: %s ' %
                 pipes.quote(' '.join(unsafe_args)))


def get_arc_root():
  return os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..'))


def get_staging_root():
  return os.path.join(OUT_DIR, 'staging')


def get_android_config_header(is_host):
  if is_host:
    arch_subdir = 'linux-x86'
  elif OPTIONS.is_arm():
    arch_subdir = 'linux-arm'
  else:
    arch_subdir = 'target_linux-x86'
  return os.path.join(get_staging_root(),
                      'android/build/core/combo/include/arch',
                      arch_subdir,
                      'AndroidConfig.h')


def get_android_fs_path(filename):
  return os.path.join(get_android_fs_root(), filename.lstrip(os.sep))


def get_android_fs_root():
  return os.path.join(get_build_dir(), 'root')


def get_android_root():
  return get_android_fs_path('system')


def get_android_sdk_ndk_dependencies():
  return [os.path.join('third_party', 'android-sdk', 'URL'),
          os.path.join('third_party', 'ndk', 'URL')]


def get_build_type():
  # Android has three build types, 'user', 'userdebug', and 'eng'.
  # 'user' is a build with limited access permissions for production.
  # 'eng' is a development configuration with debugging code. See,
  # https://source.android.com/source/building-running.html#choose-a-target.
  # ARC uses 'user' only when debug code is disabled.
  if OPTIONS.is_debug_code_enabled():
    return 'eng'
  return 'user'


def get_bare_metal_loader():
  # This function will be called even for non Bare Metal build because
  # this is used by toolchain.py, hence there is no assertion.
  return os.path.join(get_build_dir(), 'bin/bare_metal_loader')


def get_bionic_crtbegin_o():
  return os.path.join(get_load_library_path(), 'crtbegin.o')


def get_bionic_crtbegin_so_o():
  return os.path.join(get_load_library_path(), 'crtbeginS.o')


def get_bionic_crtend_o():
  return os.path.join(get_load_library_path(), 'crtend.o')


def get_bionic_crtend_so_o():
  return os.path.join(get_load_library_path(), 'crtendS.o')


def get_bionic_libc_so():
  return os.path.join(get_load_library_path(), 'libc.so')


def get_bionic_libdl_so():
  return os.path.join(get_load_library_path(), 'libdl.so')


def get_bionic_libm_so():
  return os.path.join(get_load_library_path(), 'libm.so')


def get_bionic_libstlport_so():
  return os.path.join(get_load_library_path(), 'libstlport.so')


def get_bionic_libc_malloc_debug_leak_so():
  return os.path.join(get_load_library_path(), 'libc_malloc_debug_leak.so')


def get_bionic_objects(need_stlport=True):
  return [
      get_bionic_crtbegin_o(),
      get_bionic_crtbegin_so_o(),
      get_bionic_crtend_o(),
      get_bionic_crtend_so_o(),
      get_bionic_runnable_ld_so()] + get_bionic_shared_objects(need_stlport)


def get_bionic_runnable_ld_so():
  return os.path.join(get_load_library_path(), 'runnable-ld.so')


def get_bionic_shared_objects(need_stlport=True):
  objects = [get_bionic_libc_so(),
             get_bionic_libdl_so(),
             get_bionic_libm_so()]
  if need_stlport:
    objects.append(get_bionic_libstlport_so())
  return objects


def get_bionic_arch_subdir_name():
  """Returns Bionic's architecture sub directory name.

  The architecture name is used in sub directories like
  android/bionic/libc/kernel/arch-arm.
  """

  if OPTIONS.is_arm():
    return 'arch-arm'
  else:
    return 'arch-x86'


def filter_params_for_harfbuzz(vars):
  if OPTIONS.is_nacl_x86_64() and not OPTIONS.is_optimized_build():
    # To work around nativeclient:3844, use -O1 even when --opt is not
    # specified.
    # TODO(nativeclient:3844): Remove this.
    vars.get_cflags().append('-O1')


def _get_opt_suffix():
  return '_opt' if OPTIONS.is_optimized_build() else '_dbg'


def get_target_dir_name(target):
  return target + _get_opt_suffix()


def get_build_dir(target_override=None, is_host=False):
  if is_host:
    return os.path.join(OUT_DIR, 'target', 'host' + _get_opt_suffix())
  else:
    target = target_override or OPTIONS.target()
    assert target != 'host' and target != 'java'
    return os.path.join(OUT_DIR, 'target', get_target_dir_name(target))


def get_intermediates_dir_for_library(library, is_host=False):
  """Returns intermediate output directory for the given library.

  host:  out/target/host_(dbg|opt)/intermediates/libmylib_a
  target:  out/target/<target>/intermediates/libmylib_a
  """
  basename, extension = os.path.splitext(library)
  extension = extension[1:]
  return os.path.join(get_build_dir(is_host=is_host),
                      'intermediates', basename + '_' + extension)


def get_build_path_for_library(library, is_host=False):
  """Returns intermediate build path to the given library.

  host: out/target/host_(dbg|opt)/intermediates/libmylib_a/libmylib.a
  target: out/target/<target>/intermediates/libmylib_a/libmylib.a
  """
  return os.path.join(get_intermediates_dir_for_library(
      library, is_host=is_host), library)


def get_build_path_for_executable(executable, is_host=False):
  """Returns intermediate build path to the given host executable.

  host: out/target/host_(dbg|opt)/intermediates/executable/executable
  target: out/target/<target>/intermediates/executable/executable
  """
  return os.path.join(get_build_dir(is_host=is_host),
                      'intermediates', executable, executable)


def get_build_path_for_jar(jar_name, subpath=None, is_target=False):
  root = get_target_common_dir()
  if is_target:
    root = get_build_dir()
  path = os.path.join(root, 'obj', 'JAVA_LIBRARIES',
                      jar_name + '_intermediates')
  if subpath:
    path = os.path.join(path, subpath)
  return path


def get_build_path_for_apk(apk_name, subpath=None, is_target=False):
  root = get_target_common_dir()
  if is_target:
    root = get_build_dir()
  path = os.path.join(root, 'obj', 'APPS', apk_name + '_intermediates')
  if subpath:
    path = os.path.join(path, subpath)
  return path


def get_build_tag(commit='HEAD'):
  return subprocess.check_output(
      ['git', 'describe', '--match', 'arc-runtime-*', commit]).strip()


def get_build_version(commit='HEAD'):
  return get_build_tag(commit).replace('arc-runtime-', '')


def get_chrome_default_user_data_dir():
  return '%s/%s/%s' % (os.getenv('TMPDIR', '/tmp'),
                       os.getenv('USER'),
                       CHROME_USER_DATA_DIR_PREFIX)


def get_chrome_deps_file():
  return 'src/build/DEPS.chrome'


def get_chrome_revision_by_hash(hash):
  url = ('https://chromium.googlesource.com/chromium/src'
         '/+/%s?format=JSON') % hash
  try:
    raw_data = urllib2.urlopen(url).read()
  except urllib2.URLError:
    print 'Failed to get data from: ' + url
    return None
  if raw_data.startswith(')]}\'\n'):
    raw_data = raw_data[5:]
  data = json.loads(raw_data)
  message = data['message'].replace('\n', ' ')
  m = re.match(r'.*Cr-Commit-Position: refs/heads/master@{#([0-9]+).*}',
               message)
  if m:
    return m.group(1)
  print 'Chrome revision not found for', hash
  return None


def get_prebuilt_chrome_libosmesa_path():
  return os.path.join(get_chrome_prebuilt_path(), 'libosmesa.so')


def get_chrome_exe_path_on_local_host():
  if OPTIONS.is_official_chrome():
    assert platform.system() == 'Linux', 'Only Linux is supported this time'

    if OPTIONS.chrometype() == 'dev':
      chrome_dir = 'chrome-unstable'
    elif OPTIONS.chrometype() == 'beta':
      chrome_dir = 'chrome-beta'
    else:
      chrome_dir = 'chrome'

    return os.path.join(get_chrome_prebuilt_path(),
                        'opt', 'google', chrome_dir, 'chrome')
  else:
    return os.path.join(get_chrome_prebuilt_path(), 'chrome')


def get_chrome_out_suffix():
  if OPTIONS.is_arm():
    return '-arm'
  return str(OPTIONS.get_target_bitsize())


def get_chrome_prebuilt_path():
  # Use 32-bit version of Chrome on Windows regardless of the target bit size.
  if platform_util.is_running_on_cygwin():
    return os.path.join('out', 'chrome32')
  if OPTIONS.is_x86_64():
    return os.path.join('out', 'chrome64')
  else:
    return os.path.join('out', 'chrome32')


def get_chrome_prebuilt_stamp_file():
  return os.path.join(get_chrome_prebuilt_path(), 'STAMP')


def get_chrome_ppapi_root_path():
  return os.path.join('third_party', 'chromium-ppapi')


def get_load_library_path(target_override=None):
  return os.path.join(get_build_dir(target_override), 'lib')


def get_posix_translation_readonly_fs_image_file_path():
  return os.path.join(get_build_dir(), 'posix_translation_fs_images',
                      'readonly_fs_image.img')


def get_ppapi_c_headers_dir():
  assert use_generated_ppapi_c_headers()
  return os.path.join(get_build_dir(), 'ppapi_c_headers')


def get_ppapi_c_headers_stamp():
  # When you use PPAPI C headers, you need to put this to your
  # order-only dependency.
  if use_generated_ppapi_c_headers():
    # Pretend to be a header file so that you can put this in the
    # order-only dependency.
    return [os.path.join(get_ppapi_c_headers_dir(), 'STAMP.h')]
  else:
    return []


def get_runtime_combined_out_dir():
  return os.path.join(OUT_DIR, 'target', 'common', 'runtime_combined')


def get_runtime_main_nexe():
  return os.path.join(get_build_dir(),
                      'lib/arc_%s.nexe' % OPTIONS.target())


def get_runtime_file_list():
  return os.path.join(get_build_dir(), 'runtime_file_list.txt')


def get_runtime_file_list_cc():
  return os.path.join(get_build_dir(), 'runtime_file_list.cc')


def get_runtime_out_dir():
  return os.path.join(get_build_dir(), 'runtime')


def get_handler_dir():
  # Load handler extension from src tree, because chromium can not load
  # extension with symbolic links in it.
  # TODO(penghuang): copy arc_handler to out/ during building.
  return 'src/packaging/arc_handler'


def get_runtime_version():
  runtime_tag = subprocess.check_output(
      ['git', 'describe', '--abbrev=0', '--match', 'arc-runtime-*']).strip()
  version_string = runtime_tag.replace('arc-runtime-', '')
  for part in version_string.split('.'):
    num = int(part)
    assert 0 <= num < 65535, 'runtime version out of range: ' + runtime_tag
  assert len(version_string.split('.')) <= 4
  return version_string


def get_target_common_dir():
  return os.path.join(OUT_DIR, 'target', 'common')


def get_notice_files_dir():
  return os.path.join(get_target_common_dir(), 'NOTICE_FILES')


def get_target_configure_options_file(target=None):
  return os.path.join(get_build_dir(target), 'configure.options')


def get_temp_dir():
  return os.path.join(OUT_DIR, 'tmp')


def get_test_bundle_name(commit='HEAD'):
  return 'test-bundle-%s.zip' % get_build_version(commit)


def get_thirdparty_gclient_revision_file():
  return os.path.join('third_party', '.gclient_last_sync')


def get_java_revision_file():
  return os.path.join(OUT_DIR, 'STAMP.jre')


def get_generated_ninja_dir():
  return os.path.join(OUT_DIR, 'generated_ninja')


def get_test_output_handler(use_crash_analyzer=False):
  analyzer = ''
  # Only Bionic build can be handled by crash_analyzer.
  if use_crash_analyzer:
    # Note that crash_analyzer outputs nothing if it cannot find a
    # crash message.
    analyzer = ' python src/build/crash_analyzer.py $out.tmp;'
  return _TEST_OUTPUT_HANDLER % analyzer


def get_tools_dir():
  return os.path.join(OUT_DIR, 'tools')


def get_remote_unittest_info_path(*subpath):
  return os.path.join(get_build_dir(), 'remote_unittest_info', *subpath)


def is_common_editor_tmp_file(filename):
  return bool(COMMON_EDITOR_TMP_FILE_REG.match(filename))


def rebase_path(path, current_base, requested_base):
  rel_path = os.path.relpath(path, current_base)
  return os.path.join(requested_base, rel_path)


def use_generated_ppapi_c_headers():
  return OPTIONS.is_arm()


def use_ndk_direct_execution():
  return OPTIONS.is_arm() and not OPTIONS.enable_ndk_translation()


def has_internal_checkout():
  return os.path.exists(os.path.join(_ARC_ROOT, 'internal'))


# Create a symlink from link_target to link_source, creating any necessary
# directories along the way and overwriting any existing links.
def create_link(link_target, link_source, overwrite=False):
  dirname = os.path.dirname(link_target)
  makedirs_safely(dirname)
  source_rel_path = os.path.relpath(link_source, dirname)
  if os.path.lexists(link_target):
    if overwrite:
      os.unlink(link_target)
      os.symlink(source_rel_path, link_target)
  else:
    os.symlink(source_rel_path, link_target)


class _Matcher(object):
  def __init__(self, include_re, exclude_re):
    self._include_re = include_re
    self._exclude_re = exclude_re

  def match(self, x):
    if self._exclude_re and self._exclude_re.search(x):
      return False
    if not self._include_re:
      return True
    return self._include_re.search(x)


class _MatcherFactory(object):
  def __init__(self):
    self._include_pattern_list = []
    self._exclude_pattern_list = []

  def add_inclusion(self, pattern):
    self._include_pattern_list.append(pattern)

  def add_exclusion(self, pattern):
    self._exclude_pattern_list.append(pattern)

  @staticmethod
  def _compile(pattern_list):
    if not pattern_list:
      return None
    return re.compile('|'.join(pattern_list))

  def build_matcher(self):
    return _Matcher(_MatcherFactory._compile(self._include_pattern_list),
                    _MatcherFactory._compile(self._exclude_pattern_list))


def _build_matcher(exclude_filenames, include_tests, include_suffixes,
                   include_filenames):
  factory = _MatcherFactory()

  factory.add_exclusion(COMMON_EDITOR_TMP_FILE_REG.pattern)

  for value in as_list(exclude_filenames):
    factory.add_exclusion(
        re.escape(value if '/' not in value else ('/' + value)) + '$')

  if not include_tests:
    factory.add_exclusion(re.escape('_test.'))
    factory.add_exclusion(re.escape('/tests/'))
    factory.add_exclusion(re.escape('/test_util/'))

  for value in as_list(include_suffixes):
    factory.add_inclusion(re.escape(value) + '$')

  for value in as_list(include_filenames):
    factory.add_inclusion(re.escape('/' + value) + '$')

  return factory.build_matcher()


def _generate_all_files(base_paths, matcher, use_staging, relative,
                        include_subdirectories):
  for base_path in as_list(base_paths):
    base = base_path
    if use_staging:
      base_path = os.path.join(get_staging_root(), base_path)
    for root, dirs, files in os.walk(base_path, followlinks=True):
      if not include_subdirectories:
        dirs[:] = []
      if use_staging:
        root = os.path.relpath(root, get_staging_root())
      for one_file in files:
        file_path = os.path.join(root, one_file)
        if matcher.match(file_path):
          yield file_path if not relative else os.path.relpath(file_path, base)


def find_all_files(base_paths, suffixes=None, include_tests=False,
                   use_staging=True, exclude=None, relative=False,
                   filenames=None, include_subdirectories=True):
  """Find all files under given set of base_paths matching criteria.

  If include_tests is set, any file that matches the pattern of a
  test is included, otherwise it is skipped.  The pattern of a test
  is either:
    a) basename matching *_test.*
    b) path containing a "tests" directory
  If suffixes is set, only files matching the suffix list are returned.
  If filenames is set, only filenames matching that list are returned.
  If exclude is set, only filenames not matching that list are returned.

  If relative is True, the returned paths will be relative to the base path they
  were found under.

  If use_staging is True, the input base paths will be mapped to the staging
  directory, and the files found there will be returned.
  """

  # For debugging/diffing purposes, sort the file list.
  return sorted(_generate_all_files(
      base_paths,
      matcher=_build_matcher(exclude, include_tests, suffixes, filenames),
      use_staging=use_staging, relative=relative,
      include_subdirectories=include_subdirectories))


def _get_ninja_jobs_argument():
  # -j200 might be good because having more tasks doesn't help a
  # lot and Z620 doesn't die even if everything runs locally for
  # some reason.
  return ['-j200', '-l40'] if OPTIONS.set_up_goma() else []


class RunNinjaException(Exception):
  def __init__(self, msg, cmd):
    super(RunNinjaException, self).__init__(msg)
    self.cmd = cmd


def run_ninja(args=None, cwd=None):
  cmd = ['ninja'] + _get_ninja_jobs_argument()
  if args:
    cmd = cmd + args

  res = subprocess.call(cmd, cwd=cwd)
  if res != 0:
    raise RunNinjaException('Ninja error %d' % res, ' '.join(cmd))


def find_python_dependencies(package_root_path, module_path):
  """Returns a filtered list of dependencies of a python script.

  'module_path' is the path to the python module/script to examine.

  'package_root_path' serves to identify the root of the package the module
  belongs to, and additionally is used to filter the returned dependency list to
  the list of imported files contained under it.
  """
  pythonpath = sys.path[:]
  if package_root_path not in pythonpath:
    pythonpath[0:0] = [package_root_path]
  finder = modulefinder.ModuleFinder(pythonpath)
  finder.run_script(module_path)
  dependencies = [module.__file__ for module in finder.modules.itervalues()
                  if module.__file__]

  return [path for path in dependencies
          if (path.startswith(package_root_path) and path != module_path)]


def create_tempfile_deleted_at_exit(*args, **kwargs):
  """Creates a named temporary file, which will be deleted at exit.

  The arguments of this function is as same as tempfile.NamedTemporaryFile,
  except that 'delete' param cannot be accepted.

  The result is a file-like object with 'name' attribute (as same as
  tempfile.NamedTemporaryFile).
  """
  result = tempfile.NamedTemporaryFile(delete=False, *args, **kwargs)
  atexit.register(lambda: result.unlink(result.name))
  return result


def makedirs_safely(path):
  """Ensures the specified directory exists (i.e., mkdir -p)."""
  # We should not use if os.path.isdir to avoid EEXIST because another
  # process may create the directory after we check its existence.
  try:
    os.makedirs(path)
  except OSError as e:
    if e.errno != errno.EEXIST:
      raise
  assert os.path.isdir(path)


def rmtree_with_retries(d):
  for retry_count in xrange(10):
    try:
      shutil.rmtree(d)
      break
    except:
      time.sleep(1)
      continue
  else:
    raise Exception('Failed to remove ' + d)


def read_metadata_file(path):
  """Read given metadata file into a list.

  Gets rid of leading/trailing whitespace and comments which are indicated
  with the pound/hash sign."""
  reduced_lines = []
  with open(path, 'r') as f:
    lines = f.readlines()
    for l in lines:
      l = l.strip()  # Remove trailing \n
      l = l.split('#')[0].strip()  # Remove comments
      if l:
        reduced_lines.append(l)
  return reduced_lines
