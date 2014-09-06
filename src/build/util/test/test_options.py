# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Defines an object which describes the current testing environment."""


class _TestOptions(object):
  def __init__(self):
    self.reset()

  def reset(self):
    self._is_buildbot = False
    self._supports_opengl = True
    self._want_large_tests = False

  def set_is_running_on_buildbot(self, value):
    self._is_buildbot = bool(value)

  def set_supports_opengl(self, value):
    self._supports_opengl = bool(value)

  def set_want_large_tests(self, value):
    self._want_large_tests = bool(value)

  @property
  def is_buildbot(self):
    return self._is_buildbot

  @property
  def supports_opengl(self):
    return self._supports_opengl

  @property
  def want_large_tests(self):
    return self._want_large_tests

TEST_OPTIONS = _TestOptions()
