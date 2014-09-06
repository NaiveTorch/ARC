# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


class TestMethodResult(object):
  """Represents the result of running a single test method."""
  PASS = 'P'
  FAIL = 'F'
  INCOMPLETE = 'I'
  UNKNOWN = '?'

  def __init__(self, name, code, message='', duration=0):
    self._name = name
    self._code = code
    self._message = message
    self._duration = duration

  @property
  def name(self):
    return self._name

  @property
  def duration(self):
    return self._duration

  @property
  def passed(self):
    return self._code == self.PASS

  @property
  def failed(self):
    return self._code == self.FAIL

  @property
  def incomplete(self):
    return self._code not in [self.PASS, self.FAIL]

  @property
  def message(self):
    return self._message
