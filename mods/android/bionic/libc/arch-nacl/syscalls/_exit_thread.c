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

#include <unistd.h>

#include <bionic/pthread_internal.h>
#include <irt_syscalls.h>

void _exit_thread() {
  pthread_internal_t* thread = __get_thread();
  // Let NaCl service runtime fill zero to the thread ID after
  // untrusted code finshes completely. pthread_join will wait for
  // this to check if it is safe to unmap the stack of this thread.
  //
  // nacl-glibc/nptl/pthread_create.c also lets service runtime update
  // the thread ID.
  __nacl_irt_thread_exit(&thread->tid);

  // This should not happen.
  static const int kStderrFd = 2;
  static const char kMsg[] = "__nacl_irt_thread_exit failed\n";
  write(kStderrFd, kMsg, sizeof(kMsg) - 1);

  while (1) {
#if defined(__x86_64__) || defined(__i386__)
    __asm__("hlt");
#elif defined(__arm__) && defined(BARE_METAL_BIONIC)
    __asm__("bkpt 0");
#else
#error "Unsupported architecture"
#endif
  }
}
