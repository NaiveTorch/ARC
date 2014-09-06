// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
// TODO(hamaji): Remove fprintf and this #include.
#include <stdio.h>
#include <sys/mman.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"

namespace {

int nacl_irt_mmap(void** addr, size_t len, int prot, int flags,
                  int fd, nacl_abi_off_t off) {
  // TODO(crbug.com/266627): Remove this.
#if !defined(NDEBUG)
  fprintf(stderr, "nacl_irt_mmap: addr=%p len=%zu prot=%o\n", *addr, len, prot);
#endif
  void* result = mmap(*addr, len, prot, flags, fd, off);
  // TODO(crbug.com/266627): Remove this.
#if !defined(NDEBUG)
  fprintf(stderr, "nacl_irt_mmap: result=%p\n", result);
#endif
  if (result == MAP_FAILED)
    return errno;
  *addr = result;
  return 0;
}

int nacl_irt_munmap(void* addr, size_t len) {
  int result = munmap(addr, len);
  if (result)
    return errno;
  return 0;
}

int nacl_irt_mprotect(void* addr, size_t len, int prot) {
  int result = mprotect(addr, len, prot);
  if (result)
    return errno;
  return 0;
}

extern "C" {
struct nacl_irt_memory nacl_irt_memory = {
  nacl_irt_mmap,
  nacl_irt_munmap,
  nacl_irt_mprotect,
};
}

}  // namespace
