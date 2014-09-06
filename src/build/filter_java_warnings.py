#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script exists to filter out the mandatory -Xlint warnings that
# are given when compiling upstream Android code.  Since there is
# nothing we can do about these and they just generate noise for our
# build, filter them out.  We show all other warnings and preserve
# exit status.

import filtered_subprocess
import sys
import warning_filter

my_filter = warning_filter.WarningFilter(
    r'Note: Some input files use or override a deprecated API\.',
    r'Note: .* uses or overrides a deprecated API\.',
    r'Note: Recompile with -Xlint:deprecation for details\.',
    r'Note: Some input files use unchecked or unsafe operations\.',
    r'Note: .* uses unchecked or unsafe operations\.',
    r'Note: Recompile with -Xlint:unchecked for details\.')

p = filtered_subprocess.Popen(sys.argv[1:])
p.run_process_filtering_output(my_filter)

sys.exit(p.returncode)
