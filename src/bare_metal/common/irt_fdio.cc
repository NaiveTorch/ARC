// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
// TODO(hamaji): Remove fprintf(), abort(), stdio.h, and stdlib.h.
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"
#include "bare_metal/common/nacl_stat.h"

namespace {

int nacl_irt_close(int fd) {
  int result = close(fd);
  if (result)
    return errno;
  return 0;
}

int nacl_irt_dup(int fd, int* newfd) {
  int result = dup(fd);
  if (result < 0)
    return errno;
  *newfd = result;
  return 0;
}

int nacl_irt_dup2(int fd, int newfd) {
  int result = dup2(fd, newfd);
  if (result < 0)
    return errno;
  return 0;
}

int nacl_irt_read(int fd, void* buf, size_t count, size_t* nread) {
  ssize_t result = read(fd, buf, count);
  if (result < 0)
    return errno;
  *nread = result;
  return 0;
}

int nacl_irt_write(int fd, const void* buf, size_t count, size_t* nwrote) {
  ssize_t result = write(fd, buf, count);
  if (result < 0)
    return errno;
  *nwrote = result;
  return 0;
}

int nacl_irt_seek(int fd, nacl_abi_off_t offset, int whence,
                  nacl_abi_off_t* new_offset) {
  off_t result = lseek(fd, offset, whence);
  if (result < 0)
    return errno;
  *new_offset = result;
  return 0;
}

int nacl_irt_fstat(int fd, struct nacl_abi_stat* out) {
  struct stat st;
  int result = fstat(fd, &st);
  if (result != 0)
    return errno;
  __stat_to_nacl_abi_stat(&st, out);
  return 0;
}

int nacl_irt_getdents(int /* fd */, struct dirent* /* dirp */,
                      size_t /* count */, size_t* /* nread */) {
  // TODO(crbug.com/266627): Implement this.
  fprintf(stderr, "*** nacl_irt_getdents *** is called!\n");
  abort();
}

extern "C" {
struct nacl_irt_fdio nacl_irt_fdio = {
  nacl_irt_close,
  nacl_irt_dup,
  nacl_irt_dup2,
  nacl_irt_read,
  nacl_irt_write,
  nacl_irt_seek,
  nacl_irt_fstat,
  nacl_irt_getdents,
};
}

}  // namespace
