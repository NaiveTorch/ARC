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
// Tests if a thread stack is properly unmapped when the thread exits. Since
// NaCl i686 only has 768MB of virtual address space for R/W pages, and the
// size of a thread stack is 1MB on nacl_i686, creating 800 threads should
// fails if a thread stack is not reclaimed properly.

#if defined(__native_client__)
#include <gtest/gtest.h>

#include <pthread.h>

static const size_t kNumThreads = 800;

static void* DoNothing(void*) {
  return NULL;
}

// TODO(crbug.com/362175): qemu-arm cannot reliably emulate threading
// functions so run them in a real ARM device.
#if defined(__arm__)
TEST(pthread_thread_stack, DISABLED_pthread_create_detached)
#else
TEST(pthread_thread_stack, pthread_create_detached)
#endif
{
  pthread_t thread;
  pthread_attr_t attr;
  pthread_attr_init(&attr);
  pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
  for (size_t i = 0; i < kNumThreads; ++i) {
    int ret = pthread_create(&thread, &attr, DoNothing, NULL);
    ASSERT_EQ(0, ret) << i;

    // This is a dirty hack to make the test far less flaky by helping threads
    // finish its execution quickly. If ~650 threads try to execute f() at the
    // same time (which requires 650MB of stack pages), pthread_create() would
    // fail, but we don't have a good way to limit the number of live threads.
    sched_yield();
  }
}

// TODO(crbug.com/362175): qemu-arm cannot reliably emulate threading
// functions so run them in a real ARM device.
#if defined(__arm__)
TEST(pthread_thread_stack, DISABLED_pthread_create_join)
#else
TEST(pthread_thread_stack, pthread_create_join)
#endif
{
  // Running 100 threads in parallel should be very safe in terms of free R/W
  // pages.
  static const size_t kRunThreads = 100;
  pthread_t thread[kRunThreads];

  for (size_t i = 0; i < kNumThreads / kRunThreads; ++i) {
    for (size_t j = 0; j < kRunThreads; ++j) {
      int ret = pthread_create(&thread[j], NULL, DoNothing, NULL);
      ASSERT_EQ(0, ret);
    }
    for (size_t j = 0; j < kRunThreads; ++j) {
      int ret = pthread_join(thread[j], NULL);
      ASSERT_EQ(0, ret);
    }
  }
}

static void* DetachSelf(void*) {
  pthread_detach(pthread_self());
  return NULL;
}

// TODO(crbug.com/362175): qemu-arm cannot reliably emulate threading
// functions so run them in a real ARM device.
#if defined(__arm__)
TEST(pthread_thread_stack, DISABLED_pthread_detach)
#else
TEST(pthread_thread_stack, pthread_detach)
#endif
{
  pthread_t thread;
  for (size_t i = 0; i < kNumThreads; ++i) {
    int ret = pthread_create(&thread, NULL, DetachSelf, NULL);
    ASSERT_EQ(0, ret) << i;
    sched_yield();  // see the comment above.
  }
}
#endif  // __native_client__
