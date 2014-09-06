/*
 * Copyright (C) 2008 The Android Open Source Project
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *  * Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *  * Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */

#include <errno.h>
// ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <unistd.h>  // for write.
#endif
// ARC MOD END

#include "pthread_accessor.h"

int pthread_getcpuclockid(pthread_t t, clockid_t* clockid) {
  pthread_accessor thread(t);
  if (thread.get() == NULL) {
    return ESRCH;
  }
  // ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  // NaCl and Bare Metal do not support per-thread CPU time clocks.
  static const int kStderrFd = 2;
  static const char kMsg[] = "*** pthread_getcpuclockid is called ***\n";
  write(kStderrFd, kMsg, sizeof(kMsg) - 1);
  return ENOENT;
#else
  // ARC MOD END
  // The tid is stored in the top bits, but negated.
  clockid_t result = ~static_cast<clockid_t>(thread->tid) << 3;
  // Bits 0 and 1: clock type (0 = CPUCLOCK_PROF, 1 = CPUCLOCK_VIRT, 2 = CPUCLOCK_SCHED).
  result |= 2;
  // Bit 2: thread (set) or process (clear)?
  result |= (1 << 2);

  *clockid = result;
  return 0;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
}
