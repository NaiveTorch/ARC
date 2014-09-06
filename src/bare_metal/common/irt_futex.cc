// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <linux/futex.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_futex.h"
#include "bare_metal/common/irt_interfaces.h"
#include "base/basictypes.h"
#include "bionic/libc/arch-nacl/syscalls/nacl_timespec.h"

namespace bare_metal {

void ConvertNaClAbsTimeToRelTime(const struct nacl_abi_timespec* nacl_abstime,
                                 const struct timespec* curtime,
                                 struct timespec* reltime) {
  static const int64 kNanosecondsPerSecond = 1000000000;
  int64 elapsed_nsec =
      (nacl_abstime->tv_sec - curtime->tv_sec) * kNanosecondsPerSecond +
      (nacl_abstime->tv_nsec - curtime->tv_nsec);
  // Avoid negative timeout.
  if (elapsed_nsec < 0)
    elapsed_nsec = 0;

  reltime->tv_sec = elapsed_nsec / kNanosecondsPerSecond;
  reltime->tv_nsec = elapsed_nsec % kNanosecondsPerSecond;
}

namespace {

int nacl_irt_futex_wait_abs(volatile int* addr, int value,
                            const struct nacl_abi_timespec* nacl_abstime) {
  struct timespec reltime;
  struct timespec* reltime_ptr = NULL;
  if (nacl_abstime) {
    reltime_ptr = &reltime;

    // Convert absolute time to relative time.
    struct timespec curtime;
    // We use CLOCK_REALTIME here to make compatible with NaCl service
    // runtime. NaCl service runtime uses pthread_cond_timedwait()
    // which accepts absolute time as its timeout. See
    // native_client/src/shared/platform/posix/condition_variable.c.
    if (clock_gettime(CLOCK_REALTIME, &curtime)) {
      perror("clock_gettime");
      abort();
    }
    ConvertNaClAbsTimeToRelTime(nacl_abstime, &curtime, &reltime);
  }
  int result = syscall(SYS_futex, addr, FUTEX_WAIT_PRIVATE, value, reltime_ptr,
                       NULL /* uaddr2 */, 0 /* val3 */);
  if (result)
    return errno;
  return 0;
}

int nacl_irt_futex_wake(volatile int* addr, int nwake, int* count) {
  int result = syscall(SYS_futex, addr, FUTEX_WAKE_PRIVATE, nwake,
                       NULL /* timeout */, NULL /* uaddr2 */, 0 /* val3 */);
  if (result < 0)
    return errno;
  *count = result;
  return 0;
}

extern "C" {
struct nacl_irt_futex nacl_irt_futex = {
  nacl_irt_futex_wait_abs,
  nacl_irt_futex_wake,
};
}

}  // namespace

}  // namespace bare_metal
