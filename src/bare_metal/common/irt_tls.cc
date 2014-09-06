// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <assert.h>
// TODO(hamaji): Remove fprintf and this #include.
#include <stdio.h>

#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_interfaces.h"

namespace {

__thread void* g_tls_ptr;

}  // namespace

// No namespace since we use this function from irt_thread.cc.
int nacl_irt_tls_init(void* thread_ptr) {
  // TODO(crbug.com/266627): Remove this.
#if !defined(NDEBUG)
  fprintf(stderr, "nacl_irt_tls_init %p\n", thread_ptr);
#endif
  assert(thread_ptr);
  g_tls_ptr = thread_ptr;
  return 0;
}

namespace {

void* nacl_irt_tls_get() {
  assert(g_tls_ptr);
  return g_tls_ptr;
}

extern "C" {
struct nacl_irt_tls nacl_irt_tls = {
  nacl_irt_tls_init,
  nacl_irt_tls_get,
};
}

}  // namespace
