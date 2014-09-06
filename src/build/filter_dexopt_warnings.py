#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script exists to filter out known dexopt warnings.

import filtered_subprocess
import sys
import warning_filter

_AMBIGUOUS_CLASS = 'I/libdvm.*: DexOpt: not resolving ambiguous class \'L%s;\''

my_filter = warning_filter.WarningFilter('|'.join([
    r'.*method Landroid/test/InstrumentationTestRunner\$StringResultPrinter;'
    r'\.print incorrectly overrides package-private method with same name in '
    r'Ljunit/textui/ResultPrinter;',
    # Following warnings are shown on optimizing core-libart. These warnings
    # mean that dexopt finds multiple class definitions in input jar and boot
    # classes. Actually, they are defined in both core and core-libart.
    # These warnings are also shown even on building a real Android.
    _AMBIGUOUS_CLASS % 'java/lang/Daemons\$Daemon',
    _AMBIGUOUS_CLASS % 'java/lang/Object',
    _AMBIGUOUS_CLASS % 'java/lang/reflect/AccessibleObject']))

p = filtered_subprocess.Popen(sys.argv[1:])
p.run_process_filtering_output(my_filter)

sys.exit(p.returncode)
