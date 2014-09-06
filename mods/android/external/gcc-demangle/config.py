# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import make_to_ninja


def _generate_gcc_demangle_ninja():
  def _filter(vars):
    if vars.is_host():
      return False
    if vars.is_executable():
      return False
    if vars.get_module_name() == 'libgccdemangle' and vars.is_shared():
      return False
    return True
  make_to_ninja.MakefileNinjaTranslator(
      'android/external/gcc-demangle').generate(_filter)


def generate_ninjas():
  _generate_gcc_demangle_ninja()
