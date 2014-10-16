#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import logging
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

import build_common
import toolchain
from build_options import OPTIONS
from util import platform_util

# Note: DISPLAY may be overwritten in the main() of launch_chrome.py.
__DISPLAY = os.getenv('DISPLAY')

# Consistent with NaCl's GDB stub.
_BARE_METAL_GDB_PORT = 4014

_LOCAL_HOST = '127.0.0.1'

# The default password of Chrome OS test images.
_CROS_TEST_PASSWORD = 'test0000'

# The file used to store the default Chrome OS password.
_CROS_TEST_PASSWORD_FILE = '/tmp/cros-password'

# Pretty printers for STLport.
_STLPORT_PRINTERS_PATH = ('third_party/android/ndk/sources/host-tools/'
                          'gdb-pretty-printers/stlport/gppfs-0.2')


def to_python_string_literal(s):
  return '\'%s\'' % s.encode('string-escape')


def _wait_by_busy_loop(func, interval=0.1):
  """Repeatedly calls func() until func returns value evaluated to true."""
  while True:
    result = func()
    if result:
      return result
    time.sleep(interval)


def _create_command_file(command):
  # After gdb is finished, we expect SIGINT is sent to this process.
  command = command + [';', 'kill', '-INT', str(os.getpid())]

  with build_common.create_tempfile_deleted_at_exit(
      prefix='arc-gdb-', suffix='.sh') as command_file:
    # Escape by wrapping double-quotes if an argument contains a white space.
    command_file.write(' '.join(
        '"%s"' % arg if ' ' in arg else arg for arg in command))
  os.chmod(command_file.name, stat.S_IRWXU)
  return command_file


def maybe_launch_gdb(
        gdb_target_list, gdb_type, nacl_helper_path, nacl_irt_path, chrome_pid):
  """Launches the gdb command if necessary.

  It is expected for this method to be called right after chrome is launched.
  """
  if 'browser' in gdb_target_list:
    _launch_gdb('browser', str(chrome_pid), gdb_type)

  if 'plugin' in gdb_target_list:
    if OPTIONS.is_nacl_build():
      _launch_nacl_gdb(gdb_type, nacl_irt_path)
    else:
      assert OPTIONS.is_bare_metal_build()
      if platform_util.is_running_on_chromeos():
        _launch_bare_metal_gdbserver_on_chromeos(chrome_pid)
      else:
        _launch_bare_metal_gdbserver(chrome_pid)
        _attach_bare_metal_gdb(None, [], nacl_helper_path, gdb_type)


def _get_xterm_gdb_startup(title, gdb):
  return ['xterm',
          '-display', __DISPLAY,
          '-title', title, '-e',
          gdb, '--tui',  # Run gdb with text UI mode.
          '--tty', os.ttyname(sys.stdin.fileno()),
          '-ex', 'set use-deprecated-index-sections on']


def _get_screen_gdb_startup(title, gdb):
  return ['screen',
          '-t', title,
          gdb,
          '--tty', os.ttyname(sys.stdin.fileno()),
          '-ex', 'set use-deprecated-index-sections on']


def _run_gdb_watch_thread(gdb_process):
  def _thread_callback():
    gdb_process.wait()
    # When the gdb is terminated, kill myself.
    os.kill(os.getpid(), signal.SIGINT)
  thread = threading.Thread(target=_thread_callback)
  thread.daemon = True
  thread.start()


def _launch_gdb(title, pid_string, gdb_type):
  """Launches GDB for a non-plugin process."""
  host_gdb = toolchain.get_tool('host', 'gdb')
  if gdb_type == 'xterm':
    command = _get_xterm_gdb_startup(title, host_gdb)
  elif gdb_type == 'screen':
    command = _get_screen_gdb_startup(title, host_gdb)

  command.extend(['-p', pid_string])
  if title in ('gpu', 'renderer'):
    command.extend(['-ex', r'echo To start: signal SIGUSR1\n'])
  gdb_process = subprocess.Popen(command)

  if gdb_type == 'xterm':
    _run_gdb_watch_thread(gdb_process)


def _launch_plugin_gdb(gdb_args, gdb_type):
  """Launches GDB for a plugin process."""
  gdb = toolchain.get_tool(OPTIONS.target(), 'gdb')
  if gdb_type == 'xterm':
    # For "xterm" mode, just run the gdb process.
    xterm_args = _get_xterm_gdb_startup('plugin', gdb)
    command = xterm_args + gdb_args
    gdb_process = subprocess.Popen(command)
    _run_gdb_watch_thread(gdb_process)
  elif gdb_type == 'screen':
    screen_args = _get_screen_gdb_startup('plugin', gdb)
    command = screen_args + gdb_args
    gdb_process = subprocess.Popen(command)
    print '''

=====================================================================

Now gdb should be running in another screen. Set breakpoints as you
like and start debugging by

(gdb) continue

=====================================================================
'''
  else:
    # For "wait" mode, we create a shell script and let the user know.
    command_file = _create_command_file([gdb] + gdb_args)
    print '''

=====================================================================

Now you can attach GDB. Run the following command in another shell.

$ sh %s

Then, set breakpoints as you like and start debugging by

(gdb) continue

=====================================================================

''' % command_file.name


def _is_nacl_debug_stub_ready():
  # The NaCl debug stub listens on port 4014.
  # Use netstat to check if that port is in the listening state.
  try:
    return ' 127.0.0.1:4014 ' in subprocess.check_output(
        ['netstat', '--listen', '--numeric'])
  except:
    return False


def _launch_nacl_gdb(gdb_type, nacl_irt_path):
  # Wait for nacl debug stub gets ready.
  _wait_by_busy_loop(_is_nacl_debug_stub_ready)

  nmf = os.path.join(build_common.get_runtime_out_dir(), 'arc.nmf')
  assert os.path.exists(nmf), (
      nmf + ' not found, you will have a bad time debugging')

  # TODO(nativeclient:3739): We explicitly specify the path of
  # runnable-ld.so to work-around the issue in nacl-gdb, but we should
  # let nacl-gdb find the path from NMF.
  gdb_args = [
      '-ex', 'nacl-manifest %s' % nmf,
      '-ex', 'nacl-irt %s' % nacl_irt_path,
      '-ex', 'target remote :4014',
      build_common.get_bionic_runnable_ld_so()]
  _launch_plugin_gdb(gdb_args, gdb_type)


def _get_zygote_pid(chrome_pid):
  """Returns pid of Chrome Zygote process, or None if not exist."""
  try:
    # The first column is pid, and the second param is command line.
    output = subprocess.check_output(
        ['ps', '-o', 'pid=', '-o', 'args=', '--ppid', str(chrome_pid)])
  except subprocess.CalledProcessError:
    return None

  for line in output.split('\n'):
    if '--type=zygote' in line:
      return int(line.split(None, 2)[0])
  return None


def _get_nacl_helper_nonsfi_pid(parent_pid, expected_num_processes):
  """Returns pid of nacl_helper, or None if not exist."""
  try:
    # On ARM, nacl_helper is wrapped by nacl_helper_bootstrap so the
    # exact match fails. (pgrep -x nacl_helper_bootstrap also fails
    # for some reason). So, we do not do the exact match on ARM. It
    # should be safe as ARM device (i.e., Chrome OS) does not run
    # multiple Chrome when we run launch_chrome.
    exact_flag = [] if OPTIONS.is_arm() else ['-x']
    # TODO(crbug.com/376666): Change nacl_helper to nacl_helper_nonsfi
    # and update the comment below.
    command = ['pgrep', '-P', str(parent_pid)] + exact_flag + ['nacl_helper']
    pids = subprocess.check_output(command).splitlines()
    assert len(pids) <= expected_num_processes
    # Note that we need to wait until the number of pids is equal to
    # expected_num_processes. Otherwise, we may find SFI nacl_helper
    # because Chrome launches the SFI version first and there is a
    # time window where only SFI nacl_helper is running.
    if len(pids) != expected_num_processes:
      return None
    # nacl_helper has two zygotes. One for SFI mode and the other
    # for non-SFI. As Chrome launches nacl_helper for SFI first, we
    # pick the newer PID by pgrep -n.
    command.insert(1, '-n')
    return int(subprocess.check_output(command))
  except subprocess.CalledProcessError:
    return None


def _get_bare_metal_plugin_pid(chrome_pid):
  """Waits for the nacl_helper is launched and returns its pid."""
  # The process parent-child relationship is as follows.
  #
  # ancestors
  #     ^      chrome <- directly launched from ./launch_chrome
  #     |      chrome --type=zygote
  #     |      nacl_helper <- manages plugin process fork()s.
  #     v      nacl_helper <- the plugin process we want to attach.
  # decendants
  zygote_pid = _wait_by_busy_loop(lambda: _get_zygote_pid(chrome_pid))
  logging.info('Chrome zygote PID: %d' % zygote_pid)
  nacl_helper_pid = _wait_by_busy_loop(
      lambda: _get_nacl_helper_nonsfi_pid(zygote_pid, 2))
  logging.info('nacl_helper (zygote) PID: %d' % nacl_helper_pid)
  plugin_pid = _wait_by_busy_loop(
      lambda: _get_nacl_helper_nonsfi_pid(nacl_helper_pid, 1))
  logging.info('nacl_helper (plugin) PID: %d' % plugin_pid)
  return plugin_pid


def _get_bare_metal_gdb_python_init_args():
  library_path = os.path.abspath(build_common.get_load_library_path())
  runnable_ld_path = os.path.join(library_path, 'runnable-ld.so')
  return [
      to_python_string_literal(
          os.path.join(
              library_path,
              os.path.basename(build_common.get_runtime_main_nexe()))),
      to_python_string_literal(library_path),
      to_python_string_literal(runnable_ld_path),
  ]


def _get_bare_metal_gdb_init_commands(remote_address=None, ssh_options=None):
  bare_metal_gdb_init_args = _get_bare_metal_gdb_python_init_args()
  util_dir = os.path.abspath('src/build/util')
  if remote_address:
    bare_metal_gdb_init_args.append('remote_address=%s' %
                                    to_python_string_literal(remote_address))
  if ssh_options:
    bare_metal_gdb_init_args.append(
        'ssh_options=[%s]' %
        ','.join(map(to_python_string_literal, ssh_options)))
  return ['-ex', 'python sys.path.insert(0, \'%s\')' % util_dir,
          '-ex', 'python import bare_metal_gdb',
          '-ex', 'python bare_metal_gdb.init(%s)' % (
              ', '.join(bare_metal_gdb_init_args)),
          '-ex', r'echo To start: c or cont\n']


def _attach_bare_metal_gdb(
    remote_address, ssh_options, nacl_helper_binary, gdb_type):
  """Attaches to the gdbserver running on |remote_host|.

  To conntect the server running on the local host, |remote_address| should
  be set to None, rather than '127.0.0.1' or 'localhost'. Otherwise it tries to
  re-login by ssh command as 'root' user.
  """
  # Before launching 'gdb', we wait for that the target port is opened.
  _wait_by_busy_loop(
      lambda: _is_remote_port_open(
          remote_address or _LOCAL_HOST, _BARE_METAL_GDB_PORT))

  gdb_args = [
      nacl_helper_binary,
      '-ex', 'target remote %s:%d' % (
          remote_address or _LOCAL_HOST, _BARE_METAL_GDB_PORT)
  ]
  gdb_args.extend(_get_bare_metal_gdb_init_commands(
      remote_address=remote_address, ssh_options=ssh_options))
  _launch_plugin_gdb(gdb_args, gdb_type)


def _is_remote_port_open(remote_address, port):
  with contextlib.closing(socket.socket()) as sock:
    sock.settimeout(2)
    return sock.connect_ex((remote_address, port)) == 0


def launch_bare_metal_gdb_for_remote_debug(remote_address, ssh_options,
                                           nacl_helper_binary, gdb_type):
  def _thread_callback():
    logging.info('Attaching to remote GDB in %s' % remote_address)
    _attach_bare_metal_gdb(
        remote_address, ssh_options, nacl_helper_binary, gdb_type)

  thread = threading.Thread(target=_thread_callback)
  thread.daemon = True
  thread.start()


def _launch_bare_metal_gdbserver(chrome_pid):
  # Currently we assume that, here we built -t=bi ARC. So, we use gdbserver32.
  assert OPTIONS.is_bare_metal_i686()
  plugin_pid = _get_bare_metal_plugin_pid(chrome_pid)
  command = [
      'gdbserver32', '--attach', ':%d' % _BARE_METAL_GDB_PORT, str(plugin_pid)]
  gdb_process = subprocess.Popen(command)
  _run_gdb_watch_thread(gdb_process)


def _launch_bare_metal_gdbserver_on_chromeos(chrome_pid):
  with open(_CROS_TEST_PASSWORD_FILE, 'w') as f:
    f.write(_CROS_TEST_PASSWORD + '\n')

  plugin_pid = _get_bare_metal_plugin_pid(chrome_pid)
  with open(_CROS_TEST_PASSWORD_FILE) as f:
    # Accept incoming TCP connection to the port GDB uses.
    subprocess.check_call(['sudo', '-S', '/sbin/iptables', '-A', 'INPUT',
                           '-p', 'tcp', '--dport', str(_BARE_METAL_GDB_PORT),
                           '-j', 'ACCEPT'],
                          stdin=f)

  command = ['sudo', '-S', 'gdbserver',
             '--attach', ':%d' % _BARE_METAL_GDB_PORT, str(plugin_pid)]
  with open(_CROS_TEST_PASSWORD_FILE) as f:
    gdb_process = subprocess.Popen(command, stdin=f)
  _run_gdb_watch_thread(gdb_process)


def create_or_remove_bare_metal_gdb_lock_file(gdb_target_list):
  bare_metal_gdb_lock = '/tmp/bare_metal_gdb.lock'
  if 'plugin' in gdb_target_list and OPTIONS.is_bare_metal_build():
    # Just touch the lock file.
    # TODO(crbug.com/354290): Remove this.
    with open(bare_metal_gdb_lock, 'wb'):
      pass
  else:
    # We always remove the lock file so the execution will not be
    # accidentally blocked.
    try:
      os.unlink(bare_metal_gdb_lock)
    except:
      pass


def is_no_sandbox_needed(gdb_target_list):
  """Returns whether --no-sandbox is needed to run Chrome with GDB properly.
  """
  # Chrome uses getpid() to print the PID of the renderer/gpu process to be
  # debugged, which is parsed by launch_chrome.  If the sandbox is enabled,
  # fake PIDs are returned from getpid().
  if 'renderer' in gdb_target_list or 'gpu' in gdb_target_list:
    return True

  # To suspend at the very beginning of the loader, we use a lock file.
  # no-sandox option is necessary to access the file.
  # TODO(crbug.com/354290): Remove this when GDB is properly supported.
  if OPTIONS.is_bare_metal_build() and 'plugin' in gdb_target_list:
    return True

  return False


def get_args_for_stlport_pretty_printers():
  # Disable the system wide gdbinit which may contain pretty printers for
  # other STL libraries such as libstdc++.
  gdb_args = ['-nx']

  # However, -nx also disables ~/.gdbinit. Adds it back if the file exists.
  if os.getenv('HOME'):
    user_gdb_init = os.path.join(os.getenv('HOME'), '.gdbinit')
    if os.path.exists(user_gdb_init):
      gdb_args.extend(['-x', user_gdb_init])

  # Load pretty printers for STLport.
  gdb_args.extend([
      '-ex', 'python sys.path.insert(0, "%s")' % _STLPORT_PRINTERS_PATH,
      '-ex', 'python import stlport.printers',
      '-ex', 'python stlport.printers.register_stlport_printers(None)'])

  return gdb_args


class GdbHandlerAdapter(object):
  _START_DIALOG_PATTERN = re.compile(r'(Gpu|Renderer) \((\d+)\) paused')

  def __init__(self, base_handler, target_list, gdb_type):
    assert target_list, 'No GDB target is specified.'
    self._base_handler = base_handler
    self._target_list = target_list
    self._gdb_type = gdb_type

  def handle_timeout(self):
    self._base_handler.handle_timeout()

  def handle_stdout(self, line):
    self._base_handler.handle_stdout(line)

  def handle_stderr(self, line):
    self._base_handler.handle_stderr(line)

    match = GdbHandlerAdapter._START_DIALOG_PATTERN.search(line)
    if not match:
      return

    process_type = match.group(1).lower()
    if process_type not in self._target_list:
      logging.error('%s process startup dialog found, but not a gdb target' %
                    process_type)
      return
    pid = match.group(2)
    logging.info('Found %s process (%s)' % (process_type, pid))
    _launch_gdb(process_type, pid, self._gdb_type)

  def get_error_level(self, child_level):
    return self._base_handler.get_error_level(child_level)

  def is_done(self):
    return self._base_handler.is_done()
