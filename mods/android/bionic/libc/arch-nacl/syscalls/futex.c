// Copyright (C) 2014 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// Add futex interface for Bionic.

#include <irt_syscalls.h>

#include <bionic_futex.h>
#include <errno.h>
#include <nacl_timespec.h>
#include <nacl_timeval.h>
#include <unistd.h>

int  __futex_syscall4(volatile void *ftx, int op, int val,
                      const struct timespec *timeout) {
  /* FUTEX_FD, FUTEX_REQUEUE, and FUTEX_CMP_REQUEUE are not used
   * by android.
   * TODO(crbug.com/243244): Support these operations. In theory, NDK
   * apps can call this for the operations we do not support. */
  switch (op) {
    case FUTEX_WAIT:
    case FUTEX_WAIT_PRIVATE: {
      // We need to convert the ABI of timespec from bionic's to NaCl's.
      struct nacl_abi_timespec nacl_timeout;
      struct nacl_abi_timespec *nacl_timeout_ptr = NULL;
      if (timeout) {
        // Functions from nacl-glibc expects absolute time for this.
        struct nacl_abi_timeval tv;
        int r = __nacl_irt_gettod(&tv);
        if (r != 0) {
          // Maybe this should not happen.
          return -EFAULT;
        }

        static const int kNanosecondsPerSecond = 1000000000;
        // NaClCommonSysCond_Timed_Wait_Abs does not validate timeout
        // and it has a TODO instead. So we should check the value.
        if (timeout->tv_nsec >= kNanosecondsPerSecond) {
          return -EINVAL;
        }
        long sec = timeout->tv_sec + tv.tv_sec;
        long nsec = timeout->tv_nsec + tv.tv_usec * 1000;
        sec += nsec / kNanosecondsPerSecond;
        if (sec < 0 || nsec < 0) {
          return -EINVAL;
        }
        nsec %= kNanosecondsPerSecond;
        nacl_timeout.tv_sec = sec;
        nacl_timeout.tv_nsec = nsec;
        nacl_timeout_ptr = &nacl_timeout;
      }
      // NaCL returns positive error codes, while syscalls returns negative.
      return -__nacl_irt_futex_wait_abs(ftx, val, nacl_timeout_ptr);
    }
    case FUTEX_WAKE:
    case FUTEX_WAKE_PRIVATE: {
      int count;
      // NaCl futex_wake syscall never returns an error.
      __nacl_irt_futex_wake(ftx, val, &count);
      return count;
    }
    default: {
      static const int kStderrFd = 2;
      static const char kMsg[] = "futex syscall called with unexpected op!";
      write(kStderrFd, kMsg, sizeof(kMsg) - 1);
      abort();
    }
  }
}

int __futex_syscall3(volatile void *ftx, int op, int val) {
  return __futex_syscall4(ftx, op, val, NULL);
}

int __futex_wait(volatile void *ftx, int val, const struct timespec *timeout) {
  // See third_party/android/bionic/libc/arch-x86/bionic/futex_x86.S.
  return  __futex_syscall4(ftx, FUTEX_WAIT, val, timeout);
}

int __futex_wake(volatile void *ftx, int count) {
  // See third_party/android/bionic/libc/arch-x86/bionic/futex_x86.S.
  return  __futex_syscall4(ftx, FUTEX_WAKE, count, NULL);
}
