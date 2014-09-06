// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// AutoLock for pthread_mutex_t
// TODO(crbug.com/266627): Remove this file and use AutoLock in chromium-base.
//

#ifndef BARE_METAL_COMMON_PTHREAD_AUTOLOCK_H_
#define BARE_METAL_COMMON_PTHREAD_AUTOLOCK_H_

#include <pthread.h>

#include "bare_metal/common/log.h"
#include "base/basictypes.h"

namespace bare_metal {

class PthreadAutoLock {
 public:
  explicit PthreadAutoLock(pthread_mutex_t* mutex) : mutex_(mutex) {
    CHECK(0 == pthread_mutex_lock(mutex_),  // NOLINT(readability/check)
          "pthread_mutex_lock");
  }
  ~PthreadAutoLock() {
    CHECK(0 == pthread_mutex_unlock(mutex_),  // NOLINT(readability/check)
          "pthread_mutex_unlock");
  }

 private:
  pthread_mutex_t* mutex_;

  DISALLOW_COPY_AND_ASSIGN(PthreadAutoLock);
};

}  // namespace bare_metal

#endif  // BARE_METAL_COMMON_PTHREAD_AUTOLOCK_H_
