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

#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>

#include "../../bionic/pthread_internal.h"

pthread_internal_t *__get_thread(void);

#define MAX_THREAD_ID ((1 << 15) - 1)

// 0 until the second thread other than the main thread is created.
// 2 <= g_next_tid < 32768 after the second thread is created.
// Note that bionic's mutex depends on 15 bit thread ID. See
// libc/bionic/pthread.c for detail.
static pid_t g_next_tid;
// g_tid_map[tid] will be zero if and only if the tid is not allocated.
static int8_t g_tid_map[MAX_THREAD_ID + 1];
// Protects global variables above.
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;

pid_t gettid() {
  // Defined in libc/stdlib/exit.c. Updated to 1 at the beginning of
  // pthread_create in libc/bionic/pthread.c. No lock is needed when
  // accessing this variable since pthread_create is always a memory
  // barrier as written in the __thread_entry function.
  extern int __isthreaded;

  if (!__isthreaded) {
    // The second thread is not created yet. The thread ID of the main
    // thread is always 1 on NaCl bionic. Note that we may not be able
    // to access TLS yet. We should have this test first.
    return 1;
  }

  int tid = __get_thread()->tid;
  if (tid)
    return tid;

  static const int kStderrFd = 2;
  static const char kMsg[] =
      "gettid is called for uninitialized thread\n";
  write(kStderrFd, kMsg, sizeof(kMsg) - 1);
  abort();
}

__attribute__((visibility("hidden")))
pid_t __allocate_tid() {
  pthread_mutex_lock(&g_mu);

  int cnt = 0;
  // The main thread always uses TID=1.
  while (g_next_tid < 2 || g_tid_map[g_next_tid]) {
    g_next_tid++;
    if (g_next_tid > MAX_THREAD_ID)
      g_next_tid = 1;
    // All thread IDs are being used.
    if (++cnt > MAX_THREAD_ID) {
      pthread_mutex_unlock(&g_mu);
      return -1;
    }
  }
  pid_t tid = g_next_tid;
  g_tid_map[tid] = 1;
  pthread_mutex_unlock(&g_mu);
  return tid;
}

__attribute__((visibility("hidden")))
void __deallocate_tid(pid_t tid) {
  pthread_mutex_lock(&g_mu);
  if (!g_tid_map[tid]) {
    static const int kStderrFd = 2;
    if (!tid) {
      static const char kMsg[] = "__deallocate_tid is called for tid=0\n";
      write(kStderrFd, kMsg, sizeof(kMsg) - 1);
    } else {
      static const char kMsg[] =
          "__deallocate_tid is called for uninitialized thread\n";
      write(kStderrFd, kMsg, sizeof(kMsg) - 1);
    }
    abort();
  }

  g_tid_map[tid] = 0;
  pthread_mutex_unlock(&g_mu);
}
