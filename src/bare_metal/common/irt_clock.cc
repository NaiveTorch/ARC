// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <time.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"
#include "bionic/libc/arch-nacl/syscalls/nacl_timespec.h"

namespace {

int nacl_irt_clock_getres(nacl_irt_clockid_t clk_id,
                          struct nacl_abi_timespec* out) {
  struct timespec ts;
  int result = clock_getres(clk_id, &ts);
  if (result)
    return errno;
  __timespec_to_nacl_abi_timespec(&ts, out);
  return 0;
}

int nacl_irt_clock_gettime(nacl_irt_clockid_t clk_id,
                           struct nacl_abi_timespec* out) {
  struct timespec ts;
  int result = clock_gettime(clk_id, &ts);
  if (result)
    return errno;
  __timespec_to_nacl_abi_timespec(&ts, out);
  return 0;
}

extern "C" {
struct nacl_irt_clock nacl_irt_clock = {
  nacl_irt_clock_getres,
  nacl_irt_clock_gettime,
};
}

}  // namespace
