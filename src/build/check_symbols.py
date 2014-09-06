#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Check if important symbols for NDKs are available.

import logging
import os
import subprocess
import sys

import toolchain
from build_options import OPTIONS


# Be careful when you add a symbol to this list. You must not add
# symbols which we really need to implement. For example, you should
# not add a well-known libc symbol which has a man page.
_WHITELISTS = {
    # * The libc in the Android NDK (ndk/platforms/android-19/libc.so)
    #   exports some weird internal symbols probably because it is
    #   based on an older Bionic code for some reason.
    # * On the other hand, the libc in recent Android releases
    #   (e.g. KitKat) does not export these symbols at all.
    # * Therefore, recent real Android devices always fail to load an
    #   app's NDK DSO that accidentally uses these internal symbols.
    # * In summary, whitelisting these symbols here and not having
    #   them in our Bionic does not cause compatibility issues.
    'libc.so': [
        'copy_TM_to_tm',
        'copy_tm_to_TM',
        'dlmalloc_walk_free_pages',
        'dlmalloc_walk_heap',
        'malloc_debug_init',
        'res_need_init',
        'valid_tm_mon',
        'valid_tm_wday',
    ],
    'libm.so': [
        # Recent Bionic defines this only from libc.so, but old libm.so
        # seems to have this.
        'ldexp',
    ],
}


def get_defined_symbols(filename):
  output = subprocess.check_output([toolchain.get_tool(OPTIONS.target(), 'nm'),
                                    '--defined-only', '-D', filename])
  syms = set()
  for line in output.splitlines():
    toks = line.split()
    # Empty lines or a filename line.
    if len(toks) <= 1:
      continue
    addr, sym_type, name = line.split()
    syms.add(name)
  return syms


def main():
  OPTIONS.parse_configure_file()
  logging.getLogger().setLevel(logging.INFO)

  if len(sys.argv) != 3:
    logging.fatal('Usage: %s android-lib.so arc-lib.so' % sys.argv[0])
    return 1

  android_lib = sys.argv[1]
  arc_lib = sys.argv[2]
  lib_name = os.path.basename(android_lib)

  android_syms = get_defined_symbols(android_lib)
  arc_syms = get_defined_symbols(arc_lib)

  # Explicitly check if ldexp exists in libc.so, as we allow the
  # absence of ldexp in libm.so. See also the comment for libm.so in
  # _WHITELISTS.
  if lib_name == 'libc.so' and 'ldexp' not in arc_syms:
    logging.error('ldexp must be in libc.so')
    return 1

  missing_syms = set(android_syms - arc_syms)

  whitelist = set(_WHITELISTS.get(lib_name, []))

  unused_whitelist = whitelist - missing_syms
  if unused_whitelist:
    logging.error('%s is whitelisted, but it is defined in %s. '
                  'Update _WHITELISTS' % (whitelist, arc_lib))
    return 1

  missing_syms -= whitelist

  # Most symbols starting with an underscore are internal symbols,
  # but the ones starting with '_Z' are mangled C++ symbols.
  important_missing_syms = [
      sym for sym in missing_syms
      if not sym.startswith('_') or sym.startswith('_Z')]

  if important_missing_syms:
    for sym in sorted(important_missing_syms):
      logging.error('Missing symbol: %s' % sym)
    return 1
  return 0


if __name__ == '__main__':
  sys.exit(main())
