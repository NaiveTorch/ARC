// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// A log module for Bare Metal loader.
//
// TODO(crbug.com/266627): Replace this with common/alog.h.
//

#include <stdio.h>
#include <stdlib.h>

#ifndef BARE_METAL_COMMON_LOG_H_
#define BARE_METAL_COMMON_LOG_H_

extern int g_verbosity;

#define CHECK(cond, fmt, ...)                                           \
  do {                                                                  \
    if (!(cond)) {                                                      \
      fprintf(stderr, "bm_loader: %s:%d: CHECK(%s) failed: " fmt "\n",  \
              __FILE__, __LINE__, #cond, ## __VA_ARGS__);               \
      abort();                                                          \
    }                                                                   \
  } while (0)

#define VLOG(vlevel, fmt, ...)                        \
  do {                                                \
    if (vlevel <= g_verbosity)                        \
      fprintf(stderr, "bm_loader: %s:%d: " fmt "\n",  \
              __FILE__, __LINE__, ## __VA_ARGS__);    \
  } while (0)

#endif  // BARE_METAL_COMMON_LOG_H_
