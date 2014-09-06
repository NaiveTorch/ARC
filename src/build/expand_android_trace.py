#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import build_common
import build_options
import collections
import json
import os
import re
import sys


class LogTag(object):
  def __init__(self):
    self.name = None


def main():
  build_options.OPTIONS.parse_configure_file()
  parser = argparse.ArgumentParser()

  parser.add_argument('input', nargs='?',
                      type=argparse.FileType('r'),
                      default='chrometrace.log')
  parser.add_argument('output', nargs='?',
                      type=argparse.FileType('w'),
                      default='expanded_chrometrace.log')
  parser.add_argument('--logtag', type=argparse.FileType('r'),
                      default=os.path.join(build_common.get_android_root(),
                                           'etc', 'event-log-tags'))

  options = parser.parse_args(sys.argv[1:])

  trace = json.load(options.input)

  logtag_format = re.compile(r'(\d+) (\S+) .*')
  logtags = collections.defaultdict(LogTag)
  for line in options.logtag.readlines():
    m = logtag_format.match(line)
    if m:
      logtags[int(m.group(1))].name = m.group(2)

  for i in xrange(len(trace)):
    entry = trace[i]
    if entry['cat'] == 'ARC' and entry['name'] == 'EventLogTag':
      if not 'args' in entry or not 'tag' in entry['args']:
        entry['name'] = 'Poorly formatted EventLogTag'
        print 'Invalid eventlogtag: %s' % entry
      else:
        number = entry['args']['tag']
        if not number in logtags:
          entry['name'] = 'Unknown EventLogTag'
          print 'Unknown eventlogtag: %s' % entry
        else:
          entry['name'] = logtags[number].name + " (EventLogTag)"

  options.output.write(json.dumps(trace, separators=(',', ':')))

  print 'Done'
  return 0

if __name__ == '__main__':
  sys.exit(main())
