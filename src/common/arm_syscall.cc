// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/arm_syscall.h"

#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <unistd.h>

#include "common/alog.h"

namespace arc {

namespace {

#if defined(USE_NDK_DIRECT_EXECUTION)
void RunCacheFlush(va_list ap) {
  int32_t start = va_arg(ap, int32_t);
  int32_t end = va_arg(ap, int32_t);
  uint32_t op = va_arg(ap, uint32_t);
  switch (op) {
    // Invalidate i-cache.
    case 0:
      ALOGI("icache flush: %p-%p",
            reinterpret_cast<void*>(start), reinterpret_cast<void*>(end));
      if (cacheflush(start, end, 0) != 0)
        ALOGE("cacheflush failed.");
      break;
    default:
      LOG_ALWAYS_FATAL("CacheFlush op 0x%x not supported\n", op);
  }
}
#endif

int RunArmKernelSyscallImpl(int sysno, va_list ap) {
  int result = -1;
  switch (sysno) {
    case 186:  // sigaltstack
      return -ENOSYS;
    case 224:  // gettid
      result = gettid();
      break;
    case 241:  // sched_setaffinity
      // Pretend to succeed.
      return 0;
    case kCacheFlushSysno:  // cacheflush
#if defined(USE_NDK_DIRECT_EXECUTION)
      RunCacheFlush(ap);
#else
      LOG_ALWAYS_FATAL("cacheflush must be handled in NDK translation");
#endif
      return 0;
    default:
      LOG_ALWAYS_FATAL("ARM syscall 0x%x not supported\n", sysno);
  }
  if (result < 0)
    result = -errno;
  return result;
}

}  // namespace

int RunArmKernelSyscall(int sysno, ...) {
  va_list ap;
  va_start(ap, sysno);
  int result = RunArmKernelSyscallImpl(sysno, ap);
  va_end(ap);
  return result;
}

#if defined(USE_NDK_DIRECT_EXECUTION)
int RunArmLibcSyscall(int sysno, ...) {
  va_list ap;
  va_start(ap, sysno);
  int result = RunArmKernelSyscallImpl(sysno, ap);
  va_end(ap);

  // This matches with the behavior of Bionic. See
  // third_party/android/bionic/libc/arch-arm/bionic/syscall.S.
  if (-4096 < result && result < 0) {
    errno = -result;
    return -1;
  }
  return result;
}
#endif

}  // namespace arc
