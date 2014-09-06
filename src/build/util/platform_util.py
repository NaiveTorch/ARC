# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Provides platform related functions.

import os
import sys

_LSB_RELEASE_PATH = '/etc/lsb-release'


def is_running_on_linux():
  return sys.platform.startswith('linux')


def is_running_on_cygwin():
  return sys.platform == 'cygwin'


def is_running_on_mac():
  return sys.platform == 'darwin'


def is_running_on_chromeos():
  # Check if Chrome OS specific entry exists in lsb-release file, which contains
  # Linux distribution information.
  if not os.path.exists(_LSB_RELEASE_PATH):
    return False
  with open(_LSB_RELEASE_PATH) as f:
    for line in f.readlines():
      if 'CHROMEOS_RELEASE_APPID' in line:
        return True
  return False


def get_lsb_distrib_codename():
  if not os.path.exists(_LSB_RELEASE_PATH):
    return None
  with open(_LSB_RELEASE_PATH) as f:
    for line in f:
      if line.startswith('DISTRIB_CODENAME='):
        return line.split('=')[1].strip()
  return None


def is_running_on_remote_host():
  # Currently only Cygwin (on Windows), Mac, and Chrome OS are supported as
  # remote host.
  return (is_running_on_cygwin() or
          is_running_on_mac() or
          is_running_on_chromeos())


def assert_machine(target):
  """Checks |target| is valid for the machine on which the script is running."""
  (system, _, _, _, machine) = os.uname()
  # machine is 'i686' on Windows bot which runs python installed with 32-bit
  # Cygwin even though it is running 64-bit Windows, so deal with this case
  # differently.
  if is_running_on_cygwin():
    assert target.endswith('_x86_64'), (
        'Only x86_64 target is supported on Windows')
    assert ((machine == 'x86_64') or
            (machine == 'i686' and system.endswith('WOW64'))), (
                '32-bit Windows is not supported.')
    return

  assert ((target.endswith('_arm') and machine.startswith('arm')) or
          (target.endswith('_x86_64') and machine == 'x86_64') or
          (target.endswith('_i686') and machine in ['i686', 'x86_64'])), (
              'The current ARC target (%s) is not for this machine (%s)' % (
                  target, machine))
