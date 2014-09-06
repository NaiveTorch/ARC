// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"
#include "bionic/libc/arch-nacl/syscalls/nacl_timespec.h"
#include "bionic/libc/arch-nacl/syscalls/nacl_timeval.h"

namespace {

void nacl_irt_exit(int status) {
  exit(status);
}

int nacl_irt_gettod(struct nacl_abi_timeval* out) {
  struct timeval tv;
  int result = gettimeofday(&tv, NULL);
  if (result)
    return errno;
  __timeval_to_nacl_abi_timeval(&tv, out);
  return 0;
}

int nacl_irt_clock(clock_t* /* ticks */) {
  fprintf(stderr, "*** nacl_irt_clock *** must not be called!\n");
  abort();
}

int nacl_irt_nanosleep(const struct nacl_abi_timespec* req,
                       struct nacl_abi_timespec* rem) {
  struct timespec host_req;
  struct timespec host_rem;
  __nacl_abi_timespec_to_timespec(req, &host_req);
  int result = nanosleep(&host_req, &host_rem);
  if (result)
    return errno;
  if (rem)
    __timespec_to_nacl_abi_timespec(&host_rem, rem);
  return 0;
}

int nacl_irt_sched_yield() {
  int result = sched_yield();
  if (result)
    return errno;
  return 0;
}

int nacl_irt_sysconf(int name, int* value) {
  fprintf(stderr, "*** nacl_irt_sysconf *** must not be called! "
          "name=%d value=%p\n", name, value);
  abort();
}

extern "C" {
struct nacl_irt_basic nacl_irt_basic = {
  nacl_irt_exit,
  nacl_irt_gettod,
  nacl_irt_clock,
  nacl_irt_nanosleep,
  nacl_irt_sched_yield,
  nacl_irt_sysconf,
};
}

}  // namespace
