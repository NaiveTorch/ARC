# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import make_to_ninja
import open_source
import staging


def _filter_webviewchromium(vars):
  # LOCAL_JARJAR_RULES should be defined as $(LOCAL_PATH)/jarjar-rules.txt.
  # But, webviewchromium defines it as $(CHROMIUM_PATH) relative, and
  # $(CHROMIUM_PATH) is 'external/chromium_org'. As a result, ARC can not
  # handle the file path for LOCAL_JARJAR_RULES correctly.
  # ARC manually fixes the path with 'android' prefix, and converts it to
  # a staging path.
  vars._jarjar_rules = staging.as_staging(
      os.path.join('android', vars._jarjar_rules))
  return True


def generate_ninjas():
  def _filter(vars):
    module_name = vars.get_module_name()
    if module_name == 'webviewchromium':
      return _filter_webviewchromium(vars)
    return False

  # Only Java code is built here, so nothing to do in open source.
  if open_source.is_open_source_repo():
    return
  make_to_ninja.MakefileNinjaTranslator(
      'android/frameworks/webview/chromium').generate(_filter)
