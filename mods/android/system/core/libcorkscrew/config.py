# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import make_to_ninja


def generate_ninjas():
  make_to_ninja.run_for_static('android/system/core/libcorkscrew')
