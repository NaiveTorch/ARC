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

#include <irt_syscalls.h>
#include <stdio.h>
#include <stdlib.h>

int __set_tls(void *ptr) {
  // We ask the service runtime to set the register for TLS properly
  // at the very beginning of each threads. On i686, the register is
  // %gs and the NaCl validator does not allow user code to set this
  // value.
  if (__nacl_irt_tls_init(ptr) != 0) {
    // We must not proceed the exceution when we fail to initialize
    // TLS. As stdio may not be ready now, we use pure IRT calls to
    // report the issue.
    static const char msg[] = "__nacl_irt_tls_init failed!\n";
    static const int kStderrFd = 2;
    write(kStderrFd, msg, sizeof(msg) - 1);
    exit(1);
  }
  return 0;
}
