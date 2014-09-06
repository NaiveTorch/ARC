// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// A utility function for FUTEX_WAIT.
//

#ifndef BARE_METAL_COMMON_IRT_FUTEX_H_
#define BARE_METAL_COMMON_IRT_FUTEX_H_

#include "bionic/libc/arch-nacl/syscalls/nacl_timespec.h"

namespace bare_metal {

void ConvertNaClAbsTimeToRelTime(const struct nacl_abi_timespec* nacl_abstime,
                                 const struct timespec* curtime,
                                 struct timespec* reltime);

}  // namespace bare_metal

#endif  // BARE_METAL_COMMON_IRT_FUTEX_H_
