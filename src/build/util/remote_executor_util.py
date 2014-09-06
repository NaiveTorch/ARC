# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Provides basic utilities to implement remote-host-execution of
# launch_chrome, dalvik test and run_integration_tests on Chrome OS and Windows
# (Cygwin).

import atexit
import glob
import os
import pipes
import shutil
import subprocess
import sys
import tempfile

import build_common
import filtered_subprocess
from build_options import OPTIONS
from util.minidump_filter import MinidumpFilter


RUN_UNIT_TEST = 'src/build/util/test/run_unittest.py'
SYNC_ADB = 'src/build/sync_adb.py'
SYNC_CHROME = 'src/build/sync_chrome.py'

# Following lists contain files or directories to be copied to the remote host.
_COMMON_FILE_PATTERNS = ['out/configure.options',
                         'src/build',
                         'third_party/tools/ninja/misc']
_LAUNCH_CHROME_FILE_PATTERNS = ['launch_chrome',
                                'out/target/%(target)s/runtime',
                                'src/packaging']
_INTEGRATION_TEST_FILE_PATTERNS = [
    'mods/android/dalvik/tests',
    'out/data_roots/arc.*',
    'out/data_roots/cts.*',
    'out/data_roots/dalvik.*',
    'out/data_roots/file_system_manager.*',
    'out/data_roots/gles.*',
    'out/data_roots/jstests.*',
    'out/data_roots/ndk.*',
    'out/data_roots/opaque.*',
    'out/data_roots/posix_translation.*',
    'out/data_roots/system_mode.*',
    'out/staging/android/dalvik/tests/*/expected.txt',
    'out/staging/android/dalvik/tests/*/info.txt',
    # The following two files are needed only for 401-perf test.
    'out/staging/android/dalvik/tests/401-perf/README.benchmark',
    'out/staging/android/dalvik/tests/401-perf/test_cases',
    'out/target/%(target)s/integration_tests',
    'out/target/%(target)s/root/system/usr/icu/icudt48l.dat',
    'out/target/common/dalvik_tests/*/expected.txt',
    'out/target/common/dalvik_tests/*/test*.jar',
    # TODO(crbug.com/340594): Avoid checking for APK files when CRX is
    # already generated so that we don't need to send APK to remote,
    # for package.apk, HelloAndroid.apk, glowhockey.apk, and
    # perf_tests_codec.apk
    'out/target/common/obj/APPS/GlowhockeyTest_intermediates/package.apk',
    'out/target/common/obj/APPS/HelloAndroid_intermediates/HelloAndroid.apk',
    'out/target/common/obj/APPS/ndk_translation_tests_intermediates/work/libs/*',  # NOQA
    'out/target/common/obj/APPS/perf_tests_codec_intermediates/perf_tests_codec.apk',  # NOQA
    'out/target/common/opaque/examples/opaque/glowhockey.apk',
    'out/target/common/vmHostTests',
    'run_integration_tests',
    'src/integration_tests',
    'third_party/android-cts/android-cts/repository/plans/CTS.xml',
    'third_party/android-cts/android-cts/repository/testcases/bionic-unit-tests-cts',  # NOQA
    'third_party/android-cts/android-cts/repository/testcases/*.xml',
    # Java files are needed by VMHostTestRunner, which parses java files to
    # obtain the information of the test methods at testing time.
    'third_party/android/cts/tools/vm-tests-tf/src/dot/junit/format/*/*.java',
    'third_party/android/cts/tools/vm-tests-tf/src/dot/junit/opcodes/*/*.java',
    'third_party/android/cts/tools/vm-tests-tf/src/dot/junit/verify/*/*.java',
    'third_party/ndk/sources/cxx-stl/stlport/libs/armeabi-v7a/libstlport_shared.so']  # NOQA
_UNIT_TEST_FILE_PATTERNS = ['out/target/%(target)s/bin',
                            'out/target/%(target)s/lib',
                            'out/target/%(target)s/remote_unittest_info']

# Dictionary to cache the result of remote host type auto detection.
_REMOTE_HOST_TYPE_CACHE = dict()

# Flags to launch Chrome on remote host.
_REMOTE_FLAGS = ['--nacl-helper-binary', '--remote', '--ssh-key']


_TEST_SSH_KEY = ('third_party/tools/crosutils/mod_for_test_scripts/ssh_keys/'
                 'testing_rsa')
_TEMP_DIR = None
_TEMP_KEY = 'temp_arc_key'
_TEMP_KNOWN_HOSTS = 'temp_arc_known_hosts'
# File name pattern used for ssh connection sharing (%r: remote login name,
# %h: host name, and %p: port). See man ssh_config for the detail.
_TEMP_SSH_CONTROL_PATH = 'ssh-%r@%h:%p'


def _get_temp_dir():
  global _TEMP_DIR
  if not _TEMP_DIR:
    _TEMP_DIR = tempfile.mkdtemp()
    atexit.register(lambda: build_common.rmtree_with_retries(_TEMP_DIR))
  return _TEMP_DIR


def _get_ssh_key():
  return os.path.join(_get_temp_dir(), _TEMP_KEY)


def _get_original_ssh_key():
  return os.path.join(build_common.get_arc_root(), _TEST_SSH_KEY)


def _get_known_hosts():
  return os.path.join(_get_temp_dir(), _TEMP_KNOWN_HOSTS)


def _get_ssh_control_path():
  return os.path.join(_get_temp_dir(), _TEMP_SSH_CONTROL_PATH)


class RemoteOutputHandler(object):
  """An output handler for the output from the remote host.

  This handler keeps the output from the remote host intact and prints it as-is.
  """

  def handle_timeout(self):
    pass

  def handle_stdout(self, line):
    sys.stdout.write(line)

  def handle_stderr(self, line):
    sys.stderr.write(line)

  def get_error_level(self, child_level):
    return child_level

  def is_done(self):
    return False


class RemoteExecutor(object):
  def __init__(self, user, remote, remote_env=None, ssh_key=None,
               enable_pseudo_tty=False):
    self._user = user
    self._remote_env = remote_env or {}
    if not ssh_key:
      # Copy the default ssh key and change the permissions. Otherwise ssh
      # refuses the key by saying permissions are too open.
      ssh_key = _get_ssh_key()
      if not os.path.exists(ssh_key):
        shutil.copyfile(_get_original_ssh_key(), ssh_key)
        os.chmod(ssh_key, 0400)
    self._ssh_key = ssh_key
    # Use a temporary known_hosts file
    self._known_hosts = _get_known_hosts()
    self._enable_pseudo_tty = enable_pseudo_tty
    if ':' in remote:
      self._remote, self._port = remote.split(':')
    else:
      self._remote = remote
      self._port = None

  def copy_remote_files(self, remote_files, local_dir):
    """Copies files from the remote host."""
    scp = ['scp'] + self._build_shared_command_options(port_option='-P')
    assert remote_files
    remote_file_pattern = ','.join(remote_files)
    # scp does not accept {single_file}, so we should add the brackets
    # only when multiple remote files are specified.
    if len(remote_files) > 1:
      remote_file_pattern = '{%s}' % remote_file_pattern
    scp.append('%s@%s:%s' % (self._user, self._remote, remote_file_pattern))
    scp.append(local_dir)
    run_command(scp)

  def get_remote_tmpdir(self):
    """Returns the path used as a temporary directory on the remote host."""
    return self._remote_env.get('TMPDIR', '/tmp')

  def get_remote_arc_root(self):
    """Returns the path of used as the arc root on the remote host."""
    return os.path.join(self.get_remote_tmpdir(), 'arc')

  def get_remote_env(self):
    """Returns the environmental variables for the remote host."""
    return ' '.join(
        '%s=%s' % (k, v) for (k, v) in self._remote_env.iteritems())

  def get_ssh_options(self):
    """Returns the list of options used for ssh in the runner."""
    return self._build_shared_ssh_command_options()

  def rsync(self, local_src, remote_dst):
    """Runs rsync command to copy files to remote host."""
    rsh = ' '.join(['ssh'] + self._build_shared_ssh_command_options())

    # For rsync, the order of pattern is important.
    # First, add exclude patterns to ignore common editor temporary files, and
    # .pyc files.
    # Second, add all paths to be copied.
    # Finally, add exclude '*', in order not to copy any other files.
    pattern_list = []
    for pattern in build_common.COMMON_EDITOR_TMP_FILE_PATTERNS:
      pattern_list.extend(['--exclude', pattern])
    pattern_list.extend(['--exclude', '*.pyc'])
    for path in self._build_rsync_include_pattern_list(local_src):
      pattern_list.extend(['--include', path])
    pattern_list.extend(['--exclude', '*'])

    rsync_options = [
        # The remote files need to be writable and executable by chronos. This
        # option sets read, write, and execute permissions to all users.
        '--chmod=a=rwx',
        '--copy-links',
        '--inplace',
        '--perms',
        '--progress',
        '--recursive',
        '--times']
    cmd = (['rsync', '-e', rsh] + pattern_list +
           ['.', '%s@%s:%s' % (self._user, self._remote, remote_dst)] +
           rsync_options)
    run_command(cmd)

  def run(self, cmd, ignore_failure=False, cwd=None):
    """Runs the command on remote host via ssh command."""
    if cwd is None:
      cwd = self.get_remote_arc_root()
    cmd = 'cd %s && %s' % (cwd, cmd)
    return run_command(self._build_ssh_command(cmd),
                       ignore_failure=ignore_failure)

  def run_commands(self, commands, cwd=None):
    return self.run(' && '.join(commands), cwd)

  def run_with_filter(self, cmd, cwd=None):
    if cwd is None:
      cwd = self.get_remote_arc_root()
    cmd = 'cd %s && %s' % (cwd, cmd)
    return run_command_with_filter(self._build_ssh_command(cmd))

  def run_command_for_output(self, cmd):
    """Runs the command on remote host and returns stdout as a string."""
    full_cmd = self._build_ssh_command(cmd)
    build_common.log_subprocess_popen(full_cmd)
    return subprocess.check_output(full_cmd)

  def _build_shared_command_options(self, port_option='-p'):
    """Returns command options shared among ssh and scp."""
    # By the use of Control* options, the ssh connection lives 3 seconds longer
    # so that the next ssh command can reuse it.
    result = ['-o', 'StrictHostKeyChecking=no',
              '-o', 'PasswordAuthentication=no',
              '-o', 'ControlMaster=auto', '-o', 'ControlPersist=3s',
              '-o', 'ControlPath=%s' % _get_ssh_control_path()]
    if self._port:
      result.extend([port_option, str(self._port)])
    if self._ssh_key:
      result.extend(['-i', self._ssh_key])
    if self._known_hosts:
      result.extend(['-o', 'UserKnownHostsFile=' + self._known_hosts])
    return result

  def _build_shared_ssh_command_options(self):
    """Returns command options for ssh, to be shared among run and rsync."""
    result = self._build_shared_command_options()
    # For program which requires special terminal control (e.g.,
    # run_integration_tests), we need to specify -t. Otherwise,
    # it is better to specify -T to avoid extra \r, which messes
    # up the output from locally running program.
    result.append('-t' if self._enable_pseudo_tty else '-T')
    return result

  def _build_ssh_command(self, cmd):
    ssh_cmd = (['ssh', '%s@%s' % (self._user, self._remote)] +
               self._build_shared_ssh_command_options() + ['--', cmd])
    return ssh_cmd

  def _build_rsync_include_pattern_list(self, path_list):
    pattern_set = set()
    for path in path_list:
      if os.path.isdir(path):
        # For directory, adds all files under the directory.
        pattern_set.add(os.path.join(path, '**'))

      # It is necessary to add all parent directories, otherwise some parent
      # directory won't be created and the files wouldn't be copied.
      while path:
        pattern_set.add(path)
        path = os.path.dirname(path)

    return sorted(pattern_set)


def run_command(cmd, ignore_failure=False):
  build_common.log_subprocess_popen(cmd)
  call_func = subprocess.call if ignore_failure else subprocess.check_call
  return call_func(cmd)


def run_command_with_filter(cmd):
  """Run the command with MinidumpFilter if crash reporting is enabled. """
  output_handler = RemoteOutputHandler()
  if OPTIONS.is_crash_reporting_enabled():
    output_handler = MinidumpFilter(output_handler)
  p = filtered_subprocess.Popen(cmd)
  p.run_process_filtering_output(output_handler)
  if p.returncode:
    raise subprocess.CalledProcessError(cmd, p.returncode)


def create_launch_remote_chrome_param(argv):
  """Creates flags to run ./launch_chrome on remote_host.

  To run ./launch_chrome, it is necessary to tweak the given flags.
  - Removes --nacl-helper-binary, --remote, and --ssh-key flags.
  - Adds --noninja flag.
  """
  result_argv = []
  skip_next = False
  for arg in argv:
    if skip_next:
      skip_next = False
      continue
    if arg in _REMOTE_FLAGS:
      skip_next = True
      continue
    if any(arg.startswith(flag + '=') for flag in _REMOTE_FLAGS):
      continue
    # pipes.quote should be replaced with shlex.quote on Python v3.3.
    result_argv.append(pipes.quote(arg))
  return result_argv + ['--noninja']


def create_remote_executor(parsed_args, remote_env=None,
                           enable_pseudo_tty=False):
  return RemoteExecutor(os.environ['USER'], remote=parsed_args.remote,
                        remote_env=remote_env, ssh_key=parsed_args.ssh_key,
                        enable_pseudo_tty=enable_pseudo_tty)


def get_launch_chrome_files_and_directories(parsed_args):
  patterns = (_COMMON_FILE_PATTERNS +
              _LAUNCH_CHROME_FILE_PATTERNS +
              [parsed_args.arc_data_dir])
  return _expand_target_and_glob(patterns)


def get_integration_test_files_and_directories():
  patterns = (_COMMON_FILE_PATTERNS +
              _LAUNCH_CHROME_FILE_PATTERNS +
              _INTEGRATION_TEST_FILE_PATTERNS)
  return _expand_target_and_glob(patterns)


def get_unit_test_files_and_directories(parsed_args):
  patterns = _COMMON_FILE_PATTERNS + _UNIT_TEST_FILE_PATTERNS
  return _expand_target_and_glob(patterns)


def _expand_target_and_glob(file_patterns):
  """Expands %(target)s and glob pattern in |file_patterns|.

  NOTE: This function just expands %(target)s and glob pattern and does NOT
  convert a directory path into a list of files under the directory.
  """
  format_args = {
      'target': build_common.get_target_dir_name(OPTIONS.target())
  }
  file_patterns = [pattern % format_args for pattern in file_patterns]
  paths = []
  for pattern in file_patterns:
    paths += glob.glob(pattern)
  return paths


def _detect_remote_host_type_from_uname_output(str):
  """Categorizes the output from uname -s to one of cygwin|mac|chromeos."""
  if 'CYGWIN' in str:
    return 'cygwin'
  if 'Darwin' in str:
    return 'mac'
  if 'Linux' in str:
    # We don't support non-chromeos Linux as a remote target.
    return 'chromeos'
  raise NotImplementedError('Unsupported remote host OS: %s.' % str)


def _detect_remote_host_type(remote, ssh_key):
  """Tries logging in and runs 'uname -s' to detect the host type."""
  # The 'root' users needs to be used for Chrome OS and $USER for other targets.
  # Here we try 'root' first, to give priority to Chrome OS.
  users = ['root', os.environ['USER']]
  for user in users:
    executor = RemoteExecutor(user, remote=remote, ssh_key=ssh_key)
    try:
      return _detect_remote_host_type_from_uname_output(
          executor.run_command_for_output('uname -s'))
    except subprocess.CalledProcessError:
      pass
  raise Exception(
      'Cannot remote log in by: %s\n'
      'Please check the remote address is correct: %s\n'
      'If you are trying to connect to a Chrome OS device, also check that '
      'test image (not dev image) is installed in the device.' % (
          ','.join(users), remote))


def get_remote_host_type(parsed_args):
  """Detects the remote host type or returns the cached previous result."""
  remote = parsed_args.remote
  try:
    return _REMOTE_HOST_TYPE_CACHE[remote]
  except KeyError:
    return _REMOTE_HOST_TYPE_CACHE.setdefault(
        remote, _detect_remote_host_type(remote, parsed_args.ssh_key))
