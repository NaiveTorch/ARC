# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for io.py"""

import io
import os
import unittest

from util import nonblocking_io


def _pipe():
  """Returns pipe file object."""
  (reader, writer) = os.pipe()
  return os.fdopen(reader, 'rb', 0), os.fdopen(writer, 'wb', 0)


def _read_available_lines(reader):
  """Returns all the available lines, and whether it terminates by EOF."""
  result = []
  try:
    for line in reader:
      result.append(line)
    return result, True  # Here EOF is found.
  except io.BlockingIOError:
    return result, False


class TestNonBlockingLineReader(unittest.TestCase):
  def test_regular_usage(self):
    reader, writer = _pipe()
    reader = nonblocking_io.LineReader(reader)

    # Initially, no data is available.
    self.assertRaises(io.BlockingIOError, reader.read_full_line)

    # Test single line.
    writer.write('abcde\n')
    self.assertEqual('abcde\n', reader.read_full_line())

    # Test double lines.
    writer.write('abcde\n12345\n')
    self.assertEqual('abcde\n', reader.read_full_line())
    self.assertEqual('12345\n', reader.read_full_line())

    # Test a line without trailing linesep.
    writer.write('abcde\n12345')
    self.assertEqual('abcde\n', reader.read_full_line())
    self.assertRaises(io.BlockingIOError, reader.read_full_line)

    # Again write the data. The next read_full_line() should concatenate
    # pending '12345' wrote above, and vwxyz\n.
    writer.write('vwxyz\n')
    self.assertEqual('12345vwxyz\n', reader.read_full_line())
    writer.close()

    # Opposite side is closed, so the EOF should be found.
    self.assertEqual('', reader.read_full_line())

    # The reader stream is not yet closed, even after eof.
    self.assertFalse(reader.closed)
    reader.close()
    self.assertTrue(reader.closed)

    # Calling read_full_line after close() causes ValueError.
    self.assertRaises(ValueError, reader.read_full_line)

  def test_fd(self):
    reader, writer = _pipe()
    reader_fd = reader.fileno()
    reader = nonblocking_io.LineReader(reader)
    # FD must be equal to the original one.
    self.assertEqual(reader_fd, reader.fileno())

  def test_empty(self):
    reader, writer = _pipe()
    reader = nonblocking_io.LineReader(reader)
    writer.close()
    self.assertEqual('', reader.read_full_line())

  def test_no_trailing_line_feed(self):
    reader, writer = _pipe()
    reader = nonblocking_io.LineReader(reader)

    writer.write('abcde\n12345')
    writer.close()
    self.assertEqual('abcde\n', reader.read_full_line())
    self.assertEqual('12345', reader.read_full_line())  # No \n is contained.
    self.assertEqual('', reader.read_full_line())  # EOF

  def test_read_after_close(self):
    reader, writer = _pipe()
    reader = nonblocking_io.LineReader(reader)

    writer.write('abcde\n12345\nvwxyz')
    self.assertEqual('abcde\n', reader.read_full_line())
    reader.close()

    # Closed reader must not be readable, even if there are some remaining
    # data.
    self.assertRaises(ValueError, reader.read_full_line)

  def test_iterator(self):
    reader, writer = _pipe()
    reader = nonblocking_io.LineReader(reader)

    writer.write('abcde\n12345\nvwxyz')
    read_lines, eof = _read_available_lines(reader)
    # Currenty, only 'abcde' and '12345' are available, because vwxyz may be
    # concatenated to next chunk.
    self.assertListEqual(['abcde\n', '12345\n'], read_lines)
    self.assertFalse(eof)

    writer.write('abcde\n12345')
    read_lines, eof = _read_available_lines(reader)
    self.assertListEqual(['vwxyzabcde\n'], read_lines)
    self.assertFalse(eof)

    writer.close()
    read_lines, eof = _read_available_lines(reader)
    self.assertListEqual(['12345'], read_lines)
    self.assertTrue(eof)


if __name__ == '__main__':
  unittest.main()
