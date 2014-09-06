# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This gyp stanza causes linux release builds to have debug information.
{
  'target_defaults': {
    'configurations': {
      'Release_Base': {
        'cflags': [
          '-g',
        ],
      },
    },
  },
}
