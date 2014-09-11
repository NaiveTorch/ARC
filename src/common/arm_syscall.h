// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Handles syscalls using ARM's syscall numbers.

#ifndef COMMON_ARM_SYSCALL_H_
#define COMMON_ARM_SYSCALL_H_

#include <stdarg.h>
#include <stdint.h>

namespace arc {

// See third_party/android/bionic/libc/kernel/arch-arm/asm/unistd.h.
const uint32_t kCacheFlushSysno = 0xf0002;

// Runs an ARM syscall with kernel's error handling (i.e., returns
// -errno on error).
int RunArmKernelSyscall(int sysno, ...);

#if defined(USE_NDK_DIRECT_EXECUTION)
// Runs an ARM syscall with libc's error handling (i.e, returns -1 and
// sets errno on error).
int RunArmLibcSyscall(int sysno, ...);
#endif

}  // namespace arc

#endif  // COMMON_ARM_SYSCALL_H_
