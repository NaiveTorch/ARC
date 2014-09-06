# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module contains utility to help debug across scripts."""

import sys
import traceback


def write_frames(output_stream):
  """This function prints all the stack traces of running threads."""
  output_stream.write('Dumping stack trace of all threads.\n')
  for thread_id, stack in sys._current_frames().iteritems():
    output_stream.write('Thread ID: 0x%08X\n' % thread_id)
    traceback.print_stack(stack, file=output_stream)
    output_stream.write('\n')  # Empty line to split each thread.
