#!/usr/bin/python
# Copyright (C) 2014 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Generate a linker script for runnable-ld.so.
#
# Usage:
#
# $ gen_runnable_ld_lds.py <path-to-nacl-gcc> [args-for-gcc...]
#

import re
import subprocess
import sys


def main(args):
  args.extend(['-nostdlib', '-nostartfiles', '-shared', '-Wl,--verbose'])
  # As we specify --verbose for the linker, it outputs ldscript.
  output = subprocess.check_output(args)

  # Following modifications are translated from upstream nacl-glibc.
  # See: third_party/nacl-glibc/elf/Makefile
  # TODO(https://code.google.com/p/nativeclient/issues/detail?id=3676):
  # Use the sed script in the upstream nacl-glibc.
  # The ldscript is surrounded by lines which contains only 50 equals.
  output = re.split(r'\n=+\n', output)[1]
  # nacl-glibc/elf/Makefile says sel_ldr refuses to run ld.so with
  # more than 3 loadable segments and we should remove the bss segment.
  output = re.sub(r':?seg_bss.*', '', output)
  # Move the end of .data to the end of .bss, which was removed.
  output = re.sub(r'\. = ALIGN \(CONSTANT \(MAXPAGESIZE\)\);', '', output)
  output = re.sub(r'\. = DATA_SEGMENT_END *\(\.\);', '', output)
  output = re.sub(r'(_end = \.; PROVIDE \(end = \.\);)',
                  r'\1 . = DATA_SEGMENT_END(.);', output)

  if re.search(r'OUTPUT_ARCH\(arm\)', output):
    # sel_ldr_arm refuses to load ELF executable which has multiple
    # PT_NOTE segments (.note.gnu.build-id and note.NaCl.ABI.arm). To
    # let the linker emit these two .note sections in a single segment,
    # we explicitly put .note.NaCl.ABI.arm next to .note.gnu.build-id.
    # TODO(https://code.google.com/p/nativeclient/issues/detail?id=3675):
    # Remove this once upstream NaCl fixes this issue.
    output = re.sub(r'\.note\.gnu\.build-id : { \*\(\.note\.gnu\.build-id\) }',
                    r'\g<0>\n.note.NaCl.ABI.arm : { *(.note.NaCl.ABI.arm) }',
                    output)

  print output


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
