#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Naclize i686 *.S files.

import re
import sys

import naclize_base


class Rewriter(naclize_base.RewriterBase):
  """Converts an i686 .S file to a nacl-i686 compatible one.

  You can use the rewriter as is for simple .S files, and when necessary, you
  can also implement your own rewriter for more complicated .S files by
  deriving from this class and overriding the public methods.
  """

  def __init__(self, file_name):
    naclize_base.RewriterBase.__init__(self, file_name)

  def __replace_ret(self, line):
    """Replaces ret with nacl_ret."""
    m = re.match(r'(?P<indent>\s*)ret\s*$', line)
    if m:
      self._result.append('%(indent)snaclret' % m.groupdict())
      return True
    # Replace 'ret' in lines like '# define RETURN_END ret',
    # '#define RETURN ret', and '# define RETURN ... ret; CFI_PUSH (%ebp)'
    # with 'naclret'.
    m = re.match(r'(?P<head>.*define\s+RETURN.*\s+)ret(?P<tail>(;|\s).*)$',
                 line)
    if m:
      self._result.append('%(head)snaclret%(tail)s' % m.groupdict())
    return m

  def __replace_p2align(self, line):
    """Replaces .p2align 4 with .p2align 5."""
    m = re.match(r'(?P<head>\s*\.p2align\s+)4(?P<tail>(;|\w).*)$', line)
    if m:
      self._result.append('%(head)s5%(tail)s' % m.groupdict())
    return m

  def _rewriter(self, line):
    return (self.__replace_ret(line) or
            self.__replace_p2align(line))


def main(argv):
  if len(argv) < 2:
    print 'Usage: naclize_i686.py <file_name>'
    return 1
  rewriter = Rewriter(argv[1])
  rewriter.rewrite()
  rewriter.print_result()
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv))
