# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module contains IO related utility.

Note: This module depends on fcntl package, which is available on Cygwin's
python, but not on Windows' python. Unfortunately, supporting non-blocking
read on Windows is more complicated, so we rely on fcntl for now to keep the
implementation simpler.
"""

import errno
import fcntl
import io
import os

_READ_DATA_SIZE = 4096


def _set_nonblocking(fd):
  """Set non-blocking flag to the given file descriptor."""
  flags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _read_available_data(fd):
  """Reads available data from the file descriptor.

  Returns a pair of whole read data, and a bool representing whether the stream
  is reached to EOF or not.
  The given file descriptor must be set to non-blocking mode before invocation.
  """
  result = []
  eof = False
  while True:
    try:
      # Unfortunately, the behavior of file-like object's read() on
      # non-blocking mode is not stable. E.g., file object raises an exception
      # IOError with EAGAIN, while io.FileIO returns None, if no data is
      # available. So, to avoid such inconsistency, here we use raw os.read()
      # directly.
      data = os.read(fd, _READ_DATA_SIZE)
    except EnvironmentError as e:
      if e.errno != errno.EAGAIN:  # Re-raise the exception if not EAGAIN.
        raise
      break

    if not data:
      eof = True
      break
    result.append(data)

  return ''.join(result), eof


class LineReader(object):
  """ Wraps a file-like object to allow non-blocking reads of its lines.

  This class wraps a file-like object, which provides:
    - close()
    - closed
    - fileno()
  and makes non-blocking line buffered reader.

  This class does not provide read(), readline() or readlines() unlike
  file-like objects. What this class focuses on is very close to readline() on
  non-blocking stream, but no standard behavior is defined actually. E.g.,
  io.FileIO, file object, io.BufferedReader behave differently.
  So, to avoid confusion, this class defines read_full_line() instead of
  being a file-like object. Note that this class can be iterable, too.
  """

  # Keep this in the field, in order to avoid invoking strerror a lot.
  _EAGAIN_MESSAGE = os.strerror(errno.EAGAIN)

  def __init__(self, stream):
    """Creates an non0blocking line buffered reader based on the given stream.

    stream must not be None, and must support close(), closed and fileno().
    This takes the ownership of stream, so after this function is called,
    caller must not touch stream.
    """
    assert stream
    self._stream = stream
    _set_nonblocking(stream.fileno())
    self._pending = ''
    self._lines = []

  def close(self):
    # Clear pending data.
    self._pending = None
    self._lines = None
    return self._stream.close()

  @property
  def closed(self):
    return self._stream.closed

  def fileno(self):
    return self._stream.fileno()

  def __iter__(self):
    return self

  def next(self):
    """Returns a fully read line. See read_full_line() below for details."""
    line = self.read_full_line()
    if line == '':
      raise StopIteration()
    return line

  def read_full_line(self):
    """Returns a full line if available.

    Here "full" line means a line which is terminated by os.linesep.
    If the available data does not contain os.linesep and the underlying stream
    has not reached to EOF yet, raises io.BlockingIOError.
    Note that even if the available data does not contain os.linesep, when EOF
    is found, the data will be returned.
    Empty string is a marker of EOF, as same as other file-like objects.

    Here is an example. Let 'abcde\nvwxyz' be available data:
    1) The first read_full_line() returns 'abcde\n'.
    2) The second read_full_line() raises io.BlockingIOError, because 'vwxyz'
       may be followed by more data.
    3) Then, let '12345\n67890' come to the stream.
    4) The next read_full_line() returns 'vwxyz12345\n'. Note that the leading
       data was pending 'vwxyz' at 2).
    5) Once the stream gets EOF, pending string '67890' is returned regardless
       whether it is terminated by os.linesep or not.
    6) Once the stream gets EOF, following read_full_line() invocation returns
       ''.
    """
    if self.closed:
      raise ValueError('I/O operation on closed file')

    if self._lines:
      return self._lines.pop(0)

    # Read available data from the file descriptor as much as possible.
    read_data, eof = _read_available_data(self._stream.fileno())
    if self._pending:
      read_data = self._pending + read_data
    split_lines = read_data.splitlines(True)  # Keep trailing EOL character.

    if not eof and read_data and not read_data.endswith(os.linesep):
      # More data will be followed for the last line. Keep it as pending.
      self._pending = split_lines.pop()
    else:
      self._pending = ''

    if not split_lines:
      if not eof:
        raise io.BlockingIOError(errno.EAGAIN, LineReader._EAGAIN_MESSAGE)
      return ''

    self._lines = split_lines[1:]
    return split_lines[0]
