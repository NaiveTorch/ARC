# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


class ExclusiveFlagSet(object):
  """Holds a value that is the combination of one or more _ExclusiveFlag
  values."""
  def __init__(self, value, exclusion_mask=0):
    self._value = value
    self._mask = exclusion_mask

  def __or__(self, other):
    return ExclusiveFlagSet((self._value & ~other._mask) | other._value,
                            self._mask | other._mask)

  def __contains__(self, other):
    return bool(other._value & self._value)

  def __eq__(self, other):
    return self._value == other._value

  def __iter__(self):
    for flag in _ExclusiveFlag._all_flags:
      if flag in self:
        yield flag

  def __repr__(self):
    return ','.join([repr(flag) for flag in self])

  @property
  def should_not_run(self):
    return any(flag.should_not_run for flag in self)

  @property
  def should_include_by_default(self):
    return all(flag.should_include_by_default for flag in self)


class _ExclusiveFlag(ExclusiveFlagSet):
  """Holds a single flag value, and tracks the list of all such flags."""
  _all_flags = set()

  def __init__(self, name, value, exclusion_mask=0):
    super(_ExclusiveFlag, self).__init__(value, exclusion_mask=exclusion_mask)
    self._name = name
    self._should_not_run = False
    self._should_include_by_default = True
    _ExclusiveFlag._all_flags.add(self)

  def __repr__(self):
    return self._name

  def set_should_not_run(self, value):
    self._should_not_run = bool(value)

  def set_should_include_by_default(self, value):
    self._should_include_by_default = bool(value)

  @property
  def should_not_run(self):
    return self._should_not_run

  @property
  def should_include_by_default(self):
    return self._should_include_by_default and not self._should_not_run


PASS = _ExclusiveFlag('PASS', 0x01, 0x0f)
FAIL = _ExclusiveFlag('FAIL', 0x02, 0x0f)
TIMEOUT = _ExclusiveFlag('TIMEOUT', 0x04, 0x0f)
NOT_SUPPORTED = _ExclusiveFlag('NOT_SUPPORTED', 0x08, 0x0f)
LARGE = _ExclusiveFlag('LARGE', 0x10)
FLAKY = _ExclusiveFlag('FLAKY', 0x20)
REQUIRES_OPENGL = _ExclusiveFlag('REQUIRES_OPENGL', 0x40)

VALID_FLAGS = _ExclusiveFlag._all_flags
