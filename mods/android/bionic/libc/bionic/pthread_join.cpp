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
// For __nacl_irt_sched_yield, abort, munmap, and write.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
#endif
// ARC MOD END

#include "pthread_accessor.h"

int pthread_join(pthread_t t, void** ret_val) {
  if (t == pthread_self()) {
    return EDEADLK;
  }

  pthread_accessor thread(t);
  if (thread.get() == NULL) {
      return ESRCH;
  }

  if (thread->attr.flags & PTHREAD_ATTR_FLAG_DETACHED) {
    return EINVAL;
  }

  if (thread->attr.flags & PTHREAD_ATTR_FLAG_JOINED) {
    return EINVAL;
  }

  // Signal our intention to join, and wait for the thread to exit.
  thread->attr.flags |= PTHREAD_ATTR_FLAG_JOINED;
  while ((thread->attr.flags & PTHREAD_ATTR_FLAG_ZOMBIE) == 0) {
    pthread_cond_wait(&thread->join_cond, &gThreadListLock);
  }
  if (ret_val) {
    *ret_val = thread->return_value;
  }
  // ARC MOD BEGIN
  // Unmap stack if PTHREAD_ATTR_FLAG_USER_STACK is not
  // set. Upstream bionic unmaps the stack in thread which are about
  // to exit, but we cannot do this on NaCl because the stack should
  // be available when we call __nacl_irt_thread_exit. Instead, we
  // unmap the stack from the thread which calls pthread_join.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  if (!(thread->attr.flags & PTHREAD_ATTR_FLAG_USER_STACK) &&
      thread->attr.stack_base) {
    // Wait until thread->tid becomes zero. NaCl's service runtime
    // or the Bare Metal loader do this when Bionic code for
    // |thread| finishes completely so we can safely unmap the
    // stack.
    //
    // Note that nacl-glibc's has similar code in nptl/pthread_join.c
    // and sysdeps/nacl/lowlevellock.h.
    volatile pid_t* pkernel_id = &(thread->tid);
    while (*pkernel_id) {
      // We cannot use sched_yield because it is not available in
      // libc_common.
      __nacl_irt_sched_yield();
    }

    if (munmap(thread->attr.stack_base, thread->attr.stack_size) != 0) {
      static const int kStderrFd = 2;
      static const char kMsg[] = "failed to unmap the stack!\n";
      write(kStderrFd, kMsg, sizeof(kMsg) - 1);
      abort();
    }
    // Clear the pointer to unmapped stack so pthread_join from
    // other threads will not try to unmap this region again.
    thread->attr.stack_base = NULL;
    thread->attr.stack_size = 0;
    thread->tls = NULL;
  }
#endif  // __native_client__ || BARE_METAL_BIONIC
  // ARC MOD END

  _pthread_internal_remove_locked(thread.get());
  return 0;
}
