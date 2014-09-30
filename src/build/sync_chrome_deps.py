#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Updates third_party/chromium-ppapi and third_party/native_client
# directories to match Chrome revision in DEPS.chrome.

import re
import subprocess
import sys

import build_common

_PPAPI_DIR = 'third_party/chromium-ppapi'
_NACL_DIR = 'third_party/native_client'


def main():
  with open(build_common.get_chrome_deps_file()) as f:
    chrome_hash = f.read().strip()

  if len(chrome_hash) == 6:
    chrome_revision = chrome_hash
  elif len(chrome_hash) == 40:
    chrome_revision = build_common.get_chrome_revision_by_hash(chrome_hash)
  else:
    print 'Chrome deps must be a Git hash or revision number.'
    return 1

  print 'Updating to Chrome %s (%s)' % (chrome_revision, chrome_hash)

  # Update PPAPI
  subprocess.check_call(['git', 'remote', 'update'], cwd=_PPAPI_DIR)

  # TODO(crbug.com/385310): Use chrome_hash once we start using correct repo.
  git_log_line = subprocess.check_output(
      ['git', 'log', '--remotes', '--grep',
       'Cr-Commit-Position: refs/heads/master@{#%s}' % chrome_revision,
       '-n', '1', '--oneline'],
      cwd=_PPAPI_DIR)

  m = re.match(r'([0-9,a-f]+)\s.*', git_log_line)
  if not m:
    print 'Unable to find PPAPI commit matching this Chrome revision'
    return 1
  ppapi_hash = m.group(1)

  print 'Updating PPAPI to', ppapi_hash
  subprocess.check_call(['git', 'checkout', ppapi_hash], cwd=_PPAPI_DIR)
  subprocess.check_call(['git', 'add', _PPAPI_DIR])

  # Get revision of native-client from chromium-ppapi DEPS.
  with open(_PPAPI_DIR + '/DEPS') as f:
    ppapi_deps = f.read().replace('\n', ' ')
  m = re.match(r'.*\'nacl_revision\': \'([0-9a-f]+)\',.*', ppapi_deps)
  if not m:
    print 'Unable to find NaCl deps info in', _PPAPI_DIR
    return 1
  nacl_hash = m.group(1)

  print 'Updating NACL to', nacl_hash
  subprocess.check_call(['git', 'remote', 'update'], cwd=_NACL_DIR)
  subprocess.check_call(['git', 'checkout', nacl_hash], cwd=_NACL_DIR)
  subprocess.check_call(['git', 'add', _NACL_DIR])

  print 'Update completed successfully'
  return 0

if __name__ == '__main__':
  sys.exit(main())
