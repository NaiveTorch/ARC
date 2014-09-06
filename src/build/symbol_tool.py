#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Usage:
#
# 1) Dump defined symbols
# $ ./src/build/symbol_tool --dump-defined foo.so > defined.list
#
# 2) Dump undefined symbols
# $ ./src/build/symbol_tool --dump-undefined foo.so > undefined.list
#
# 3) Clean up symbols file (remove comments and sort)
# $ ./src/build/symbol_tool --clean foo.list > clean.list
#
# 4) Verify symbols
# $ ./src/build/symbol_tool --verify input.list disallowed.list
#    (Reports errors if input.list contains symbols listed in disallowed.list)
#

import argparse
import subprocess
import sys
import toolchain

from build_options import OPTIONS


def main():
  description = 'Tool to manipulate symbol list files.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument(
      '--dump-defined', action='store_true',
      help='Dump defined symbols from the given shared object.')
  parser.add_argument(
      '--dump-undefined', action='store_true',
      help='Dump defined symbols from the given shared object.')
  parser.add_argument(
      '--clean', action='store_true',
      help='Copy symbols file with comments stripped.')
  parser.add_argument(
      '--verify', action='store_true',
      help='Verify that file 1 does not contain symbols listed in file 2.')
  parser.add_argument('args', nargs=argparse.REMAINDER)

  args = parser.parse_args()

  OPTIONS.parse_configure_file()
  nm = toolchain.get_tool(OPTIONS.target(), 'nm')

  if args.dump_defined:
    command = (nm + ' --defined-only --extern-only --format=posix %s | '
               'sed -n \'s/^\(.*\) [A-Za-z].*$/\\1/p\' | '
               'LC_ALL=C sort -u' % args.args[0])
    return subprocess.check_call(command, shell=True)

  elif args.dump_undefined:
    command = (nm + ' --undefined-only --format=posix %s | '
               'sed -n \'s/^\(.*\) U.*$/\\1/p\' | '
               'LC_ALL=C sort -u' % args.args[0])
    return subprocess.check_call(command, shell=True)

  elif args.clean:
    command = ('egrep -ve "^#" %s | LC_ALL=C sort' % args.args[0])
    return subprocess.check_call(command, shell=True)

  elif args.verify:
    command = ('LC_ALL=C comm -12 %s %s' % (args.args[0], args.args[1]))
    try:
      diff = subprocess.check_output(command, shell=True,
                                     stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
      # This can happen if files are not sorted
      print e.output.rstrip()
      return 1
    if diff:
      print '%s has disallowed symbols: ' % (args.args[0])
      print diff.rstrip()
      return 1
    return 0

  print 'No command specified.'
  return 1


if __name__ == '__main__':
  sys.exit(main())
