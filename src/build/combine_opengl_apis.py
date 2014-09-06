#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# ARC MOD IGNORE: Since we generate arc mod regions.

import re
import sys

seen_functions = []

print """/* ARC MOD BEGIN FORK */
// This file was auto-generated using:
//   %s
// DO NOT EDIT.""" % ' '.join(sys.argv)

for infile in sys.argv[1:]:
  with open(infile, 'r') as f:
    print '\n// Entries from ' + infile + '\n'
    lines = f.readlines()
    while lines:
      line = lines.pop(0)
      m = re.search(r'API_ENTRY\(([^\)]+)\)', line)
      if m:
        if not m.group(1) in seen_functions:
          sys.stdout.write(line)
          sys.stdout.write(lines.pop(0))
          sys.stdout.write(lines.pop(0))
          seen_functions.append(m.group(1))
        else:
          lines.pop(0)
          lines.pop(0)

print """/* ARC MOD END FORK */"""
