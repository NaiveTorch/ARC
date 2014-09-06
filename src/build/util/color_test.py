#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import StringIO
import unittest

from util import color


class MockStream(object):
  """Thin wrapper of StringIO to emulate tty stream."""
  def __init__(self):
    self._isatty = False
    self.output = StringIO.StringIO()

  def write(self, text):
    self.output.write(text)

  def close(self):
    self.output.close()

  def getvalue(self):
    return self.output.getvalue()

  def isatty(self):
    return self._isatty


class TestColorUtil(unittest.TestCase):
  """Tests the evaluation of the input configuration."""

  TEXT = '99 bottles of beer'

  def test_write_ansi_escape(self):
    # If stream is a tty, the text should be formatted with escape sequence.
    stream = MockStream()
    stream._isatty = True
    color.write_ansi_escape(stream, color.RED, TestColorUtil.TEXT)
    self.assertEqual('\x1b[31;1m99 bottles of beer\x1b[m', stream.getvalue())
    stream.close()

    # If stream is not a tty, the text should be output to the stream as is.
    stream = MockStream()
    color.write_ansi_escape(stream, color.RED, TestColorUtil.TEXT)
    self.assertEqual(TestColorUtil.TEXT, stream.getvalue())
    stream.close()

    # It is legal to pass None for |escape|.
    stream = MockStream()
    color.write_ansi_escape(stream, None, TestColorUtil.TEXT)
    self.assertEqual(TestColorUtil.TEXT, stream.getvalue())
    stream.close()
