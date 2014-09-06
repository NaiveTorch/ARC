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
// Define writev. Note that this code is very similar to
// src/posix_translation/file_stream.cc.

#include <errno.h>
#include <limits.h>
#include <sys/uio.h>

int writev(int fd, const struct iovec *iov, int count) {
  if (count < 0 || count > UIO_MAXIOV) {
    errno = EINVAL;
    return -1;
  }

  size_t total = 0;
  for (int i = 0; i < count; i++) {
    if (iov[i].iov_len > SSIZE_MAX - total) {
      errno = EINVAL;
      return -1;
    }
    total += iov[i].iov_len;
  }
  if (total == 0)
    return 0;

  char *buffer;
  // We use alloca when the buffer we need is small. This is mandatory
  // because some writev calls in the Bionic loader happens before we
  // initialize malloc. This means all writev calls in the Bionic
  // loader should not output more than 4096 bytes.
  static const int kMaxAllocaSize = 4096;
  if (total > kMaxAllocaSize)
    buffer = (char *)malloc(total);
  else
    buffer = (char *)alloca(total);
  size_t offset = 0;
  for (int i = 0; i < count; i++) {
    memcpy(&buffer[offset], iov[i].iov_base, iov[i].iov_len);
    offset += iov[i].iov_len;
  }
  int nwrote = write(fd, buffer, total);
  if (total > kMaxAllocaSize)
    free(buffer);
  return nwrote;
}
