#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Generate wrapped_functions.cc, which contains the list of wrapped functions.
#

import string
import sys

sys.path.insert(0, 'src/build')

import wrapped_functions
from build_options import OPTIONS


_WRAPPED_FUNCTIONS_CC_TEMPLATE = string.Template("""
// Auto-generated file - DO NOT EDIT!

#include "common/wrapped_functions.h"
#include "common/wrapped_function_declarations.h"

namespace arc {

WrappedFunction kWrappedFunctions[] = {
${WRAPPED_FUNCTIONS}
  { 0, 0 }
};

}  // namespace arc
""")


def main():
  OPTIONS.parse_configure_file()

  functions = []
  for function in wrapped_functions.get_wrapped_functions():
    functions.append('  { "%s", reinterpret_cast<void*>(%s) },' %
                     (function, function))
  sys.stdout.write(_WRAPPED_FUNCTIONS_CC_TEMPLATE.substitute({
      'WRAPPED_FUNCTIONS': '\n'.join(functions)
  }))


if __name__ == '__main__':
  sys.exit(main())
