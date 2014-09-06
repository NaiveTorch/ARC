#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Generate android_static_libraries.cc, which contains the list of
# statically linked Android libraries.
#

import os
import string
import sys

sys.path.insert(0, 'src/build')

import android_static_libraries
from build_options import OPTIONS


_ANDROID_STATIC_LIBRARIES_TEMPLATE = string.Template("""
// Auto-generated file - DO NOT EDIT!

#include "common/android_static_libraries.h"
#include <stddef.h>

namespace arc {

const char* kAndroidStaticLibraries[] = {
${ANDROID_STATIC_LIBRARIES}
  NULL
};

}  // namespace arc
""")


def main():
  OPTIONS.parse_configure_file()

  libs = []
  for lib in android_static_libraries.get_android_static_library_deps():
    assert lib.endswith('.a')
    lib = os.path.splitext(lib)[0]

    # Strip unnecessary suffixes (e.g., libjpeg_static).
    for unnecessary_suffix in ['_static', '_fake']:
      if lib.endswith(unnecessary_suffix):
        lib = lib[:-len(unnecessary_suffix)]
    libs.append(lib)

  # We are not building android/frameworks/native/opengl/libs/GLES2.
  # As libGLESv2.so is just a wrapper of real GL implementations, GL
  # related symbols linked in the main nexe work as symbols in
  # libGLESv2.so.
  libs.append('libGLESv2')

  # Graphics translation builds all EGL/GLES libraries as static libraries
  # so we need to register them here so that they can still be dlopen'ed.
  if not OPTIONS.enable_emugl():
    libs.append('libEGL')
    libs.append('libEGL_emulation')
    libs.append('libGLESv1_CM')
    libs.append('libGLESv2_emulation')

  libs_string_literals = ['  "%s",' % lib for lib in libs]

  sys.stdout.write(_ANDROID_STATIC_LIBRARIES_TEMPLATE.substitute({
      'ANDROID_STATIC_LIBRARIES': '\n'.join(libs_string_literals)
  }))


if __name__ == '__main__':
  sys.exit(main())
