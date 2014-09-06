// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"
#include "bare_metal/common/nacl_stat.h"

namespace {

int nacl_irt_open(const char *pathname, int oflag, mode_t cmode, int *newfd) {
  // TODO(crbug.com/266627): Translate |oflag|.
  int fd = open(pathname, oflag, cmode);
  if (fd < 0)
    return errno;
  *newfd = fd;
  return 0;
}

int nacl_irt_stat(const char* pathname, struct nacl_abi_stat* out) {
  struct stat st;
  int result = stat(pathname, &st);
  if (result != 0)
    return errno;
  __stat_to_nacl_abi_stat(&st, out);
  return 0;
}

extern "C" {
struct nacl_irt_filename nacl_irt_filename = {
  nacl_irt_open,
  nacl_irt_stat,
};
}

}  // namespace
