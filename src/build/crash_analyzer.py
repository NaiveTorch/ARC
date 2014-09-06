#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Usage:
#
# $ src/build/crash_analyzer.py
#   out/target/nacl_i686/intermediates/bionic_test/bionic_test.results.1.tmp
#
# Note that this is also integrated in launch_chrome.py.
#

import argparse
import os
import re
import subprocess
import sys
import toolchain

import build_common
from build_options import OPTIONS


class CrashAnalyzer(object):
  def __init__(self, is_annotating=False):
    self._text_segments = []
    self._crash_addr = None
    # A map from basename to path of binaries. Loaded lazily when
    # crash is found.
    self._binary_map = None
    self._is_annotating = is_annotating

  def handle_line(self, line):
    if self._is_annotating:
      sys.stdout.write(line)

    line = line.strip()
    matched = re.match(
        r'linker: Loaded text: 0x([0-9a-f]+)-0x([0-9a-f]+) (.*)', line)
    if matched:
      start_addr = int(matched.group(1), 16)
      end_addr = int(matched.group(2), 16)
      binary_name = matched.group(3)
      self._text_segments.append((binary_name, start_addr, end_addr))
      return False

    if self._is_annotating:
      addr_reg = r'.*0x([0-9a-f]+)'
    else:
      addr_reg = r'\*\* Signal \d+ from untrusted code: pc=([0-9a-f]+)'

    matched = re.match(addr_reg, line)
    if matched:
      self._crash_addr = int(matched.group(1), 16)
      # Convert 64bit address to 32bit for x86-64.
      self._crash_addr &= (1 << 32) - 1
      return True

    return False

  def init_binary_map(self):
    if self._binary_map:
      return

    self._binary_map = {}
    for dirpath, dirnames, filenames in (
        os.walk(build_common.get_load_library_path())):
      for filename in filenames:
        if filename.endswith('.nexe'):
          name = '/lib/main.nexe'
        else:
          name = os.path.basename(filename)
        if name in self._binary_map:
          raise Exception('Duplicated binary: ' + name)
        self._binary_map[name] = os.path.join(dirpath, filename)

  def get_crash_report(self):
    assert self._crash_addr is not None
    for binary_name, start_addr, end_addr in self._text_segments:
      if start_addr > self._crash_addr or self._crash_addr >= end_addr:
        continue

      addr = self._crash_addr
      # For PIC or PIE, we need to subtract the load bias.
      if binary_name.endswith('.so') or OPTIONS.is_bare_metal_build():
        addr -= start_addr

      if os.path.exists(binary_name):
        binary_filename = binary_name
      else:
        self.init_binary_map()
        if binary_name not in self._binary_map:
          return '%s %x (binary file not found)\n' % (binary_name, addr)
        binary_filename = self._binary_map[binary_name]

      pipe = subprocess.Popen([toolchain.get_tool(OPTIONS.target(),
                                                  'addr2line'),
                               '-e', binary_filename],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
      addr2line_result = pipe.communicate('%x\n' % addr)[0]

      # We can always get clean result using 32 byte aligned start
      # address as NaCl binary does never overlap 32 byte boundary.
      objdump_start_addr = (addr & ~31) - 32
      objdump_end_addr = addr + 64
      pipe = subprocess.Popen([toolchain.get_tool(OPTIONS.target(),
                                                  'objdump'),
                               '-SC', binary_filename,
                               '--start-address', '0x%x' % objdump_start_addr,
                               '--stop-address', '0x%x' % objdump_end_addr],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
      objdump_result = pipe.communicate('%x\n' % addr)[0]

      if self._is_annotating:
        report = ('[[ %s 0x%x %s ]]' %
                  (binary_filename, addr, addr2line_result.strip()))
        # The result of objdump is too verbose for annotation.
      else:
        report = '%s 0x%x\n' % (binary_filename, addr)
        report += addr2line_result
        report += objdump_result

      return report
    return 'Failed to retrieve a crash report\n'


def _parse_args():
  parser = argparse.ArgumentParser()
  parser.add_argument('--annotate', action='store_true',
                      help='All hex values which start with 0x will be '
                      'annotated.')
  parser.add_argument('target_files', nargs='*')
  return parser.parse_args()


def main():
  OPTIONS.parse_configure_file()
  args = _parse_args()
  for arg in args.target_files:
    with open(arg) as f:
      analyzer = CrashAnalyzer(is_annotating=args.annotate)
      for line in f:
        if analyzer.handle_line(line):
          print analyzer.get_crash_report()


if __name__ == '__main__':
  sys.exit(main())
