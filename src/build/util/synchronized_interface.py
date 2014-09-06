# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Synchronizes calls to a class instance/interface.

Ensures all calls to made to an instance or interface are synchronized, and that
the only access made is through function calls.
"""

import threading


class Synchronized(object):
  def __init__(self, underlying):
    self.__lock = threading.Lock()
    self.__underlying = underlying

  def __getattr__(self, name):
    value = getattr(self.__underlying, name)
    if callable(value):
      def wrapper(*args, **kwargs):
        with self.__lock:
          return value(*args, **kwargs)
      return wrapper
    raise NotImplementedError('Attributes of type %s are not supported. '
                              '(%s was accessed on the underlying instance)' %
                              (type(value), name))
