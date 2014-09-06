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
// Checks if the loader can relocate a function and load a program.
//

#include <private/nacl_syscalls.h>
#include <string.h>

static void nacl_syscall_exit(int status) {
  NACL_SYSCALL(exit)(status);
}

static void nacl_syscall_write(int fd, const void *buf, int count) {
  NACL_SYSCALL(write)(fd, buf, count);
}

static void print_str(const char* s) {
  int cnt = 0;
  const char* p;
  for (p = s; *p; p++)
    cnt++;
  nacl_syscall_write(2, s, cnt);
}

void _start() {
  print_str("Started\n");
  char buf[256];
  // As we are not in main(), IRT table is not ready, so we cannot
  // check the relocation by write. We will use strcpy instead.
  strcpy(buf, "Relocation is OK\n");
  print_str(buf);
  print_str("PASS\n");
  nacl_syscall_exit(0);
}
