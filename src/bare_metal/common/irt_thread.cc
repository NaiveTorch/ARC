// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"

int nacl_irt_tls_init(void* thread_ptr);

namespace {

// We heuristically chose 1M for the stack size per thread.
const int kStackSize = 1024 * 1024;

void Fail(const char* msg) {
  perror(msg);
  abort();
}

struct ThreadContext {
  void (*start_func)();
  void* thread_ptr;
};

void* RunThread(void* data) {
  ThreadContext* context = static_cast<ThreadContext*>(data);
  void (*start_func)() = context->start_func;
  void *thread_ptr = context->thread_ptr;
  nacl_irt_tls_init(thread_ptr);
  delete context;
  start_func();
  return NULL;
}

int nacl_irt_thread_create(void (*start_func)(), void* stack,
                           void* thread_ptr) {
  pthread_attr_t attr;
  if (pthread_attr_init(&attr))
    Fail("pthread_attr_init");

  // Note: Currently we ignore the argument stack.
  if (pthread_attr_setstacksize(&attr, kStackSize))
    Fail("pthread_attr_setstacksize");

  if (pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED))
    Fail("pthread_attr_setdetachstate");

  pthread_t thread;
  ThreadContext* context = new ThreadContext;
  context->start_func = start_func;
  context->thread_ptr = thread_ptr;
  if (pthread_create(&thread, &attr, &RunThread, context)) {
    if (pthread_attr_destroy(&attr))
      Fail("pthread_attr_destroy");
    return errno;
  }

  if (pthread_attr_destroy(&attr))
    Fail("pthread_attr_destroy");
  return 0;
}

void nacl_irt_thread_exit(int32_t* stack_flag) {
  // As we actually don't use stack given to thread_create, it means that the
  // memory can be released whenever.
  if (stack_flag)
    *stack_flag = 0;
  pthread_exit(NULL);
}

int nacl_irt_thread_nice(const int val) {
  fprintf(stderr, "*** nacl_irt_thread_nice *** must not be called! val=%d\n",
          val);
  abort();
}

extern "C" {
struct nacl_irt_thread nacl_irt_thread = {
  nacl_irt_thread_create,
  nacl_irt_thread_exit,
  nacl_irt_thread_nice,
};
}

}  // namespace
