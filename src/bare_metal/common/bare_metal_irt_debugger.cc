// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <assert.h>
#include <elf.h>
#include <link.h>
#include <pthread.h>
#include <string.h>

#include <algorithm>

#include "bare_metal/common/bare_metal_irt.h"
#include "bare_metal/common/irt.h"
#include "bare_metal/common/log.h"

namespace bare_metal {

// We do nothing in these functions. We will set breakpoints for these
// functions to let GDB load shared objects.

void bare_metal_irt_notify_gdb_of_load(link_map* lm) {
  VLOG(1, "bare_metal_irt_notify_gdb_of_load %s", lm->l_name);
}

void bare_metal_irt_notify_gdb_of_unload(link_map* lm) {
  VLOG(1, "bare_metal_irt_notify_gdb_of_unload %s", lm->l_name);
}

void bare_metal_irt_notify_gdb_of_libraries() {
  VLOG(1, "bare_metal_irt_notify_gdb_of_libraries");
}

namespace {

extern "C" {
struct bare_metal_irt_debugger bare_metal_irt_debugger = {
  bare_metal_irt_notify_gdb_of_load,
  bare_metal_irt_notify_gdb_of_unload,
  bare_metal_irt_notify_gdb_of_libraries,
};
}

}  // namespace

}  // namespace bare_metal
