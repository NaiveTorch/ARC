# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Build libchromium_net library."""

import make_to_ninja


def _generate_chromium_net_ninja():
  def _filter(vars):
    if vars.get_module_name() == 'libchromium_net':
      make_to_ninja.Filters.convert_to_static_lib(vars)
    return True

  make_to_ninja.MakefileNinjaTranslator(
      'android/external/chromium').generate(_filter)


def generate_ninjas():
  _generate_chromium_net_ninja()
