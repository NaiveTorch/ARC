// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Declare Bare Metal specific IRT interfaces.
//

#ifndef BARE_METAL_COMMON_BARE_METAL_IRT_H_
#define BARE_METAL_COMMON_BARE_METAL_IRT_H_

// Note that including link.h does not work when this header is
// included from Bionic because Bionic's link.h does not have the
// declaration of link_map. Use a forward declaration instead.
#if defined(__cplusplus)
extern "C"
#endif
struct link_map;

// We use this declaration only from C++ code.
#if defined(__cplusplus)
namespace bare_metal {
void bare_metal_irt_notify_gdb_of_load(struct link_map* lm);
}  // namespace bare_metal
#endif

#define BARE_METAL_IRT_DEBUGGER_v0_1 "bare-metal-irt-debugger-0.1"
struct bare_metal_irt_debugger {
  void (*notify_gdb_of_load)(struct link_map* map);
  void (*notify_gdb_of_unload)(struct link_map* map);
  void (*notify_gdb_of_libraries)();
};

#endif  // BARE_METAL_COMMON_BARE_METAL_IRT_H_
