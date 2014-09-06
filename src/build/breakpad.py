#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import hashlib
import logging
import multiprocessing
import os
import subprocess
import sys

import build_common
import toolchain
from build_options import OPTIONS
from util import concurrent


_MINIDUMP_DUMP_TOOL = toolchain.get_nacl_tool('minidump_dump')
_DUMP_SYMS_TOOL = build_common.get_build_path_for_executable('dump_syms',
                                                             is_host=True)
_MINIDUMP_STACKWALK_TOOL = toolchain.get_nacl_tool('minidump_stackwalk')
_SYMBOL_OUT_DIR = 'out/symbols'


def _get_symbol_marker(path):
  sha1 = hashlib.sha1()
  with open(path) as f:
    sha1.update(f.read())
  return os.path.join(_SYMBOL_OUT_DIR, 'hash', sha1.hexdigest())


def _extract_symbols_from_one_binary(binary):
  # If the marker is already written, we should already have the
  # extracted symbols.
  marker_path = _get_symbol_marker(binary)
  if os.path.exists(marker_path):
    logging.info('Skip extracting symbols from: %s' % binary)
    return

  logging.info('Extracting symbols from: %s' % binary)
  syms = subprocess.check_output([_DUMP_SYMS_TOOL, binary])
  # The first line should look like:
  # MODULE Linux arm 0222CE01F27D6870B1FA991F84B9E0460 libc.so
  symhash = syms.splitlines()[0].split()[3]
  base = os.path.basename(binary)
  sympath = os.path.join(_SYMBOL_OUT_DIR, base, symhash, base + '.sym')
  build_common.makedirs_safely(os.path.dirname(sympath))

  with open(sympath, 'w') as f:
    f.write(syms)

  # Create the marker directory so we will not need to extract symbols
  # in the next time.
  build_common.makedirs_safely(marker_path)


def _extract_symbols():
  # Extract symbols in parallel.
  with concurrent.ThreadPoolExecutor(
      max_workers=multiprocessing.cpu_count(), daemon=True) as executor:
    for root, _, filenames in os.walk(build_common.get_load_library_path()):
      for filename in filenames:
        if os.path.splitext(filename)[1] in ['.so', '.nexe']:
          executor.submit(_extract_symbols_from_one_binary,
                          os.path.join(root, filename))


def _stackwalk(minidump):
  _extract_symbols()
  subprocess.check_call([_MINIDUMP_STACKWALK_TOOL, minidump, _SYMBOL_OUT_DIR])


def _dump(minidump):
  subprocess.check_call([_MINIDUMP_DUMP_TOOL, minidump])


def _parse_args():
  parser = argparse.ArgumentParser()
  parser.add_argument('mode', choices=('stackwalk', 'dump'))
  parser.add_argument('minidump', type=str, metavar='<file>',
                      help='The minidump file to be analyzed.')
  return parser.parse_args()


def main():
  OPTIONS.parse_configure_file()
  args = _parse_args()
  if args.mode == 'stackwalk':
    _stackwalk(args.minidump)
  elif args.mode == 'dump':
    _dump(args.minidump)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  sys.exit(main())
