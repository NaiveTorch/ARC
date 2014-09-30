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

#include <errno.h>
#include <irt_syscalls.h>
#include <unistd.h>

int getdents(unsigned int fd, struct dirent* dirp, unsigned int count) {
  // NaCl's dirent is different from Bionic's. Notably, NaCl's seems
  // to lack d_type field. Without d_type, we cannot implement
  // directory functions compatible with Android. So, we ignore NaCl's
  // ABI and always use Bionic's.
  size_t nread;
  int result = __nacl_irt_getdents(fd, dirp, count, &nread);
  if (result != 0) {
    errno = result;
    return -1;
  }
  return nread;
}
