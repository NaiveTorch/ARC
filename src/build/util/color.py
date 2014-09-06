#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import curses
import os
import sys

# TODO(lpique): Rename this module as output_format or something similar.


class AnsiEscape(object):
  ANSI_CSI = '\x1b['

  def __init__(self, begin_sequence=None, end_sequence=None):
    self.begin = AnsiEscape.ANSI_CSI + begin_sequence if begin_sequence else ''
    self.end = AnsiEscape.ANSI_CSI + end_sequence if end_sequence else ''


CURSOR_TO_LINE_BEGIN = AnsiEscape(begin_sequence='1G')
CLEAR_TO_LINE_END = AnsiEscape(begin_sequence='0K')


class Color(AnsiEscape):
  def __init__(self, fg_color=None, bg_color=None):
    # The format of the escape sequence with "Select Graphics Rendition" is
    # "\x1b[<SGR parameters>m". <SGR parameters> is a list of decimal integers
    # split by ';'. Specifically, 30-39 represent a foreground color, 40-49
    # represent a background color, and 1 represents 'BOLD'.
    sgr_params = []
    if fg_color is not None:
      sgr_params.append(str(30 + fg_color))
    if bg_color is not None:
      sgr_params.append(str(40 + bg_color))
    if sgr_params:
      sgr_params.append('1')  # Increase the instenstity.
    super(Color, self).__init__(
        begin_sequence=';'.join(sgr_params) + 'm',
        end_sequence='m')


RED = Color(fg_color=curses.COLOR_RED)
GREEN = Color(fg_color=curses.COLOR_GREEN)
YELLOW = Color(fg_color=curses.COLOR_YELLOW)
BLUE = Color(fg_color=curses.COLOR_BLUE)
MAGENTA = Color(fg_color=curses.COLOR_MAGENTA)
CYAN = Color(fg_color=curses.COLOR_CYAN)
# Bright black means GRAY.
GRAY = Color(fg_color=curses.COLOR_BLACK)
WHITE = Color(fg_color=curses.COLOR_WHITE)

WHITE_ON_RED = Color(fg_color=curses.COLOR_WHITE, bg_color=curses.COLOR_RED)
WHITE_ON_GREEN = Color(fg_color=curses.COLOR_WHITE,
                       bg_color=curses.COLOR_GREEN)
WHITE_ON_YELLOW = Color(fg_color=curses.COLOR_WHITE,
                        bg_color=curses.COLOR_YELLOW)
WHITE_ON_BLUE = Color(fg_color=curses.COLOR_WHITE, bg_color=curses.COLOR_BLUE)
WHITE_ON_MAGENTA = Color(fg_color=curses.COLOR_WHITE,
                         bg_color=curses.COLOR_MAGENTA)
WHITE_ON_CYAN = Color(fg_color=curses.COLOR_WHITE,
                      bg_color=curses.COLOR_CYAN)


def write_ansi_escape(output, escape, text):
  # Apply |escape| only when output is a tty device.
  if escape and output.isatty():
    output.write(escape.begin)
    output.write(text)
    output.write(escape.end)
  else:
    output.write(text)


_DEFAULT_TERMINAL_WIDTH = 80
if os.name == 'posix':  # Should cover Linux, Darwin
  import fcntl
  import struct
  import termios

  def get_terminal_width():
    columns = None
    try:
      s = struct.pack('HHHH', 0, 0, 0, 0)
      t = fcntl.ioctl(sys.stdout, termios.TIOCGWINSZ, s)
      unused_rows, columns, unused_pad, unused_pad = struct.unpack('HHHH', t)
    except IOError:
      pass
    if not columns:
      columns = int(os.getenv('COLUMNS', _DEFAULT_TERMINAL_WIDTH))
    return columns
else:
  def get_terminal_width():
    # TODO(lpique): For Windows there is another way.....
    return _DEFAULT_TERMINAL_WIDTH
