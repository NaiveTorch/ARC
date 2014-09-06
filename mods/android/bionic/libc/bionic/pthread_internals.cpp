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

#include "pthread_internal.h"
/* ARC MOD BEGIN */

#include <sys/mman.h>
#include <stdlib.h>
#include <unistd.h>
/* ARC MOD END */

#include "bionic_tls.h"
#include "ScopedPthreadMutexLocker.h"

__LIBC_HIDDEN__ pthread_internal_t* gThreadList = NULL;
__LIBC_HIDDEN__ pthread_mutex_t gThreadListLock = PTHREAD_MUTEX_INITIALIZER;

void _pthread_internal_remove_locked(pthread_internal_t* thread) {
  if (thread->next != NULL) {
    thread->next->prev = thread->prev;
  }
  if (thread->prev != NULL) {
    thread->prev->next = thread->next;
  } else {
    gThreadList = thread->next;
  }

  // The main thread is not heap-allocated. See __libc_init_tls for the declaration,
  // and __libc_init_common for the point where it's added to the thread list.
  if (thread->allocated_on_heap) {
    free(thread);
  }
}

__LIBC_ABI_PRIVATE__ void _pthread_internal_add(pthread_internal_t* thread) {
  ScopedPthreadMutexLocker locker(&gThreadListLock);

  // We insert at the head.
  thread->next = gThreadList;
  thread->prev = NULL;
  if (thread->next != NULL) {
    thread->next->prev = thread;
  }
  gThreadList = thread;
}

__LIBC_ABI_PRIVATE__ pthread_internal_t* __get_thread(void) {
  void** tls = reinterpret_cast<void**>(const_cast<void*>(__get_tls()));
  return reinterpret_cast<pthread_internal_t*>(tls[TLS_SLOT_THREAD_ID]);
}
/* ARC MOD BEGIN */
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
// On NaCl and Bare Metal, a thread stack and pthread_internal_t struct for
// a detached thread must be released after the thread completely finishes.
// Define two functions for that. Details below:
// _pthread_internal_prepend_detached_threads_locked is called when
// pthread_exit is called for a detached thread to add the thread to
// |gDetachedFinishedThreadList|. _pthread_internal_free_detached_threads
// is called every time when pthread_exit is called (regardless of whether
// or not the exiting thread is detached) to actually free pthread_internal_t
// structures for such detached threads.

static pthread_internal_t* gDetachedFinishedThreadList = NULL;

void _pthread_internal_free_detached_threads(void) {
  ScopedPthreadMutexLocker locker(&gThreadListLock);

  pthread_internal_t* thread = gDetachedFinishedThreadList;
  while (thread) {
    volatile pid_t* pkernel_id = &(thread->tid);
    pthread_internal_t* next = thread->next;
    // NaCl service runtime writes zero to |tid| when the thread
    // completely finishes.
    if (*pkernel_id == 0) {
      if (!(thread->attr.flags & PTHREAD_ATTR_FLAG_USER_STACK) &&
          thread->attr.stack_base) {
        if (munmap(thread->attr.stack_base,
                   thread->attr.stack_size) != 0) {
          static const int kStderrFd = 2;
          static const char kMsg[] = "failed to unmap the stack!\n";
          write(kStderrFd, kMsg, sizeof(kMsg) - 1);
          abort();
        }
      }

      // The following code is very similar to the one in
      // _pthread_internal_remove_locked().
      if (next)
        next->prev = thread->prev;
      if (thread->prev)
        thread->prev->next = next;
      else
        gDetachedFinishedThreadList = next;
      if (thread->allocated_on_heap)
        free(thread);
    }
    thread = next;
  }
}

void _pthread_internal_prepend_detached_threads_locked(pthread_internal_t* thread) {
  if (thread->tid == 0)  // sanity check.
    abort();

  // Remove |thread| from |gThreadList|.
  const bool orig = thread->allocated_on_heap;
  thread->allocated_on_heap = false;  // to prevent |thread| from being freed.
  _pthread_internal_remove_locked(thread);
  thread->allocated_on_heap = orig;

  // ..and then add it to |gDetachedFinishedThreadList|.
  thread->next = gDetachedFinishedThreadList;
  thread->prev = NULL;
  if (thread->next)
    thread->next->prev = thread;
  gDetachedFinishedThreadList = thread;
}
#endif  // __native_client__ || BARE_METAL_BIONIC
/* ARC MOD END */
