#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Check consistency between --wrap for the linker and defined symbols.

import re
import subprocess
import sys

import toolchain
import wrapped_functions
from build_options import OPTIONS


def _get_defined_functions(library):
  nm = toolchain.get_tool(OPTIONS.target(), 'nm')
  nm_output = subprocess.check_output([nm, '-D', '--defined-only', library])

  functions = []
  for line in nm_output.splitlines():
    matched = re.search(r' [TW] (\w+)', line)
    if matched:
      functions.append(matched.group(1))
  return functions


def _check_wrapper_functions_are_defined(functions, arc_nexe):
  arc_nexe_funcs = _get_defined_functions(arc_nexe)
  wrapper_funcs = set()
  for func in arc_nexe_funcs:
    if func.startswith('__wrap_'):
      wrapper_funcs.add(func.replace('__wrap_', ''))

  ok = True
  for func in sorted(functions - wrapper_funcs):
    ok = False
    print ('--wrap=%s is specified in wrapped_functions.py, '
           'but __wrap_%s is not defined in arc.nexe' % (func, func))

  # We internally use them to implement IRT wrappers.
  whitelist = set(['close',
                   'getcwd',
                   'lseek64',
                   'open',
                   'read',
                   'write'])

  for func in sorted(wrapper_funcs - functions - whitelist):
    ok = False
    print ('--wrap=%s is not specified in wrapped_functions.py, '
           'but __wrap_%s is defined in arc.nexe' % (func, func))

  return ok


def _check_wrapped_functions_are_defined(functions, libc_libraries):
  def _get_whitelist():
    # They are glibc-only functions, but we provide wrappers for them
    # as they might be added to Bionic in future.
    # TODO(crbug.com/350701): Remove them once we have removed glibc
    # support and had some kind of check for symbols in Bionic.
    return ['epoll_create1',
            'epoll_pwait',
            'inotify_init1',
            'mkostemp',
            'mkostemps',
            'ppoll',
            'preadv',
            'pwritev']

  libc_funcs = set()
  for lib in libc_libraries:
    libc_funcs |= set(_get_defined_functions(lib))

  ok = True
  for func in sorted(functions - libc_funcs - set(_get_whitelist())):
    ok = False
    print ('--wrap=%s is specified in wrapped_functions.py, '
           'but __wrap_%s is not defined in libc' % (func, func))

  return ok


def main():
  OPTIONS.parse_configure_file()

  if len(sys.argv) < 3:
    print 'Usage: %s arc.nexe libc.so...'
    return 1

  arc_nexe = sys.argv[1]
  libc_libraries = sys.argv[2:]
  functions = set(wrapped_functions.get_wrapped_functions())

  ok = _check_wrapper_functions_are_defined(functions, arc_nexe)
  ok = ok & _check_wrapped_functions_are_defined(functions, libc_libraries)
  if not ok:
    print 'FAILED'
    return 1
  print 'OK'
  return 0


if __name__ == '__main__':
  sys.exit(main())
