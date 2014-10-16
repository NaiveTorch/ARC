#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Tool to make a table of contents file of a shared library in a build rule.
# The output file contains the list of all external symbols of the shared
# library.  So dependants that is linked dynamically to the shared library
# needs to be relink only when the contents of the output file is modified.
#
# This script updates the timestamp of the output file only when its content
# is updated.  So that the build system can stop re-building a dependant that is
# dynamically linked to the shared library.
#

import errno
import subprocess
import sys

import build_common
import toolchain


def make_table_of_contents(target, input_so_path):
  # List only external dynamic symbol as implied by '-g' and '-D'.
  # Use posix format of output that implied by '-f','p' as it is easiest to
  # parse for our usage.
  external_symbols = subprocess.check_output([
      toolchain.get_tool(target, 'nm'), '-gD', '-f', 'p', input_so_path
  ])
  symbols = []
  for line in external_symbols.splitlines():
    # |line| should contain:
    # <symbol name> <symbol type> <address>
    # Put symbol names and symbol types into the TOC file.
    # Drop address part since its modification does not require relinking for
    # binaries that are dynamically linked agaist |input_so_path|.
    symbols.append(' '.join(line.split(' ')[:2]))

  return '\n'.join(symbols)


def should_update_toc_file(toc, output_toc_path):
  """Returns True if |output_toc_path| needs to be updated with |toc|."""
  # Update |output_toc_path| unless |output_toc_path| exists and its content is
  # exactly the same as |toc|.
  try:
    with open(output_toc_path, 'r') as f:
      return f.read() != toc
  except IOError as (error, _):
    # The output file is not found.  The output file should be created in this
    # case, since this is the first invocation of the script after the shared
    # library is created.
    if error == errno.ENOENT:
      return True
    raise


def main(args):
  if len(args) != 3:
    return -1

  target = args[0]
  input_so_path = args[1]
  output_toc_path = args[2]
  toc = make_table_of_contents(target, input_so_path)

  if should_update_toc_file(toc, output_toc_path):
    build_common.write_atomically(output_toc_path, toc)
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
