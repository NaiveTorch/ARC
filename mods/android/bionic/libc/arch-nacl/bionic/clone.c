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
//
// Defines __pthread_clone, which creates a new thread.
//

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>

#include <bionic_tls.h>
#include <irt_syscalls.h>

// We use these slots to pass the thread function and its argument as
// these slots are not used during the initialization of threads.
#define TLS_SLOT_THREAD_FUNC TLS_SLOT_OPENGL_API
#define TLS_SLOT_THREAD_ARGS TLS_SLOT_OPENGL

void __thread_entry(int (*func)(void *), void *arg, void **tls);

// The entry point of new threads.
static void run_thread() {
  void **tls = (void **)__nacl_irt_tls_get();
  int (*fn)(void *) = (int (*)(void *))tls[TLS_SLOT_THREAD_FUNC];
  void *arg = tls[TLS_SLOT_THREAD_ARGS];
  tls[TLS_SLOT_THREAD_FUNC] = tls[TLS_SLOT_THREAD_ARGS] = NULL;
  __thread_entry(fn, arg, tls);
}

pid_t __allocate_tid();

int __pthread_clone(int (*fn)(void*), void **tls, int flags, void *arg)
{
  int tid = __allocate_tid();
  if (tid < 0) {
    errno = ENOMEM;
    return -1;
  }

  // The stack will be put before TLS.
  // See the comment of pthread_create in libc/bionic/pthread.c for detail.
  void **child_stack = (void **)(((uintptr_t)tls & ~15));

  // Pass |fn| and |arg| using TLS.
  tls[TLS_SLOT_THREAD_FUNC] = fn;
  tls[TLS_SLOT_THREAD_ARGS] = arg;
  int result = __nacl_irt_thread_create(&run_thread, child_stack, tls);
  if (result != 0) {
    errno = result;
    return -1;
  }
  return tid;
}
