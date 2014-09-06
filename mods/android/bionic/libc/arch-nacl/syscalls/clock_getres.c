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
// Unfortunately, nacl-glibc's clock_getres.c is heavily depending on
// other code in glibc. So, we track nothing for this file.
//

#include <errno.h>
#include <time.h>

#include <irt_syscalls.h>
#include <nacl_timespec.h>

int clock_getres(clockid_t clk_id, struct timespec *res) {
  switch (clk_id) {
    case CLOCK_MONOTONIC:
    case CLOCK_PROCESS_CPUTIME_ID:
    case CLOCK_REALTIME:
    case CLOCK_THREAD_CPUTIME_ID: {
      struct nacl_abi_timespec nacl_res;
      int result = __nacl_irt_clock_getres(clk_id, &nacl_res);
      if (result != 0) {
        errno = result;
        return -1;
      }
      // The manual says res==NULL is OK.
      if (res)
        __nacl_abi_timespec_to_timespec(&nacl_res, res);
      return 0;
    }
    default:
      errno = EINVAL;
      return -1;
  }
}
