# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import make_to_ninja
import open_source


def generate_ninjas():
  def _filter(vars):
    if vars.is_static_java_library():
      return False

    module_name = vars.get_module_name()
    assert module_name == 'core-junit', module_name
    assert vars.is_java_library()
    return True

  if open_source.is_open_source_repo():
    # We currently do not build Java code in open source.
    return
  make_to_ninja.MakefileNinjaTranslator(
      'android/external/junit').generate(_filter)
