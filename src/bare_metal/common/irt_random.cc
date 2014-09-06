// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"
#include "base/basictypes.h"
#include "base/posix/eintr_wrapper.h"

namespace {

class ScopedFd {
 public:
  explicit ScopedFd(int fd) : fd_(fd) {}

  ~ScopedFd() {
    if (fd_ >= 0) {
      if (close(fd_) != 0 && errno != EINTR)
        abort();
    }
  }

  int fd() const { return fd_; }

 private:
  int fd_;

  DISALLOW_COPY_AND_ASSIGN(ScopedFd);
};

int nacl_irt_get_random_bytes(void* buf, size_t count, size_t* nread) {
  ScopedFd fd(open("/dev/urandom", O_RDONLY));
  if (fd.fd() < 0)
    abort();
  size_t result = HANDLE_EINTR(read(fd.fd(), buf, count));
  if (result != count)
    abort();
  *nread = result;
  return 0;
}

extern "C" {
struct nacl_irt_random nacl_irt_random = {
  nacl_irt_get_random_bytes,
};
}

}  // namespace
