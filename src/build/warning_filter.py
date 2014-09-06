# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This file defines a filter class appropriate for passing to
# filtered_process.py as an output filter.  The class provides a way
# to filter out known warnings from third-party code which we will not
# attempt to fix.  For a usage example, see filter_java_warnings.py.

import re
import sys


class WarningFilter(object):
  def __init__(self, *warning_re_strings):
    """Create a process filter class filtering out the given warnings.

    warning_re is a list of regular expression strings.  Any line
    matching one of these strings is filtered out of the process'
    output.
    """
    self._warning_re = re.compile('|'.join(warning_re_strings))

  def _has_warning(self, line):
    return self._warning_re.match(line) is not None

  def handle_stdout(self, line):
    if not self._has_warning(line):
      sys.stdout.write(line)

  def handle_stderr(self, line):
    if not self._has_warning(line):
      sys.stderr.write(line)

  def is_done(self):
    return False

  def handle_timeout(self):
    pass
