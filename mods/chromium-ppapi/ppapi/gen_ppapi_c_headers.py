#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Modify PPAPI headers to adjust calling convention for floating point
# on ARM so that softfp code can call PPAPI functions.

import os
import re
import sys


# The implementations of PPAPI functions are defined in the helper
# binary, for which we always use -mfloat-abi=hard where the default
# calling convention is "aapcs-vfp". To call these functions from
# "softfp", whose default calling convention is "aapcs", we need to
# specify a special attribute. See this document for these attributes.
# http://gcc.gnu.org/onlinedocs/gcc/Function-Attributes.html
#
# FYI, "aapcs" stands for ARM architecture procedure calling standard.
_ATTRIBUTE_HARD_CALLING_CONVENTION = '__attribute__((pcs("aapcs-vfp")))'
_COPYRIGHT = 'Copyright 2014 The Chromium Authors. All rights reserved.'


def _convert_header(input_header, output_header):
  # To avoid generating half-baked files, we output to a temporary
  # file first, then rename it.
  tmp_output = output_header + '.tmp'
  with open(input_header) as input_stream:
    with open(tmp_output, 'w') as output_stream:
      output_stream.write('// %s\n'
                          '\n'
                          '// Do not edit! Auto-generated using:\n'
                          '//  %s\n\n' % (_COPYRIGHT, ' '.join(sys.argv)))

      for line in input_stream:
        # This matches function pointers in arguments or
        # typedefs. This is intentional. Callback functions you pass
        # to bare_metal_helper should have the __attribute__ if the
        # function has floating point parameters. Unfortunately,
        # compiler does not enforce this check. As of Feb. 2014,
        # PPAPI has no callback functions which have floating point
        # arguments so this should be fine.
        if re.match(r'[^()]+ \(\*[^()]+\)\s*\(', line):
          output_stream.write(_ATTRIBUTE_HARD_CALLING_CONVENTION)
        output_stream.write(line)
  os.rename(tmp_output, output_header)


def main():
  input_file = sys.argv[1]
  output_file = sys.argv[2]
  _convert_header(input_file, output_file)


if __name__ == '__main__':
  sys.exit(main())
