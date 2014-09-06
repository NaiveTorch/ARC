# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libjnigraphics.so."""

import make_to_ninja


def generate_ninjas():
  make_to_ninja.run('android/frameworks/base/native/graphics/jni')
