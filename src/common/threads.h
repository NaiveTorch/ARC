// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMMON_THREADS_H_
#define COMMON_THREADS_H_

#include <sys/prctl.h>  // For setting thread names.

#include "common/trace_event.h"

namespace arc {

inline void SetThreadDebugName(const char* name, bool tell_trace) {
  prctl(PR_SET_NAME, name, 0, 0, 0);
  if (tell_trace)
    trace::SetThreadName(name);
}

}  // namespace arc

#endif  // COMMON_THREADS_H_
