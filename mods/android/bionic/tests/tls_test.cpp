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

#include <gtest/gtest.h>

#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#endif
#include <pthread.h>

TEST(tls, basic) {
  pthread_key_t key;
  ASSERT_EQ(0, pthread_key_create(&key, NULL));
  const void* ptr = &key;
  ASSERT_EQ(0, pthread_setspecific(key, ptr));
  const void* result = pthread_getspecific(key);
  EXPECT_EQ(result, ptr);
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  // Check if our assembly code in __get_tls() agrees with NaClSysTlsGet.
  const void** tls = reinterpret_cast<const void**>(__nacl_irt_tls_get());
  // See pthread_getspecific() in bionic/libc/bionic/pthread.c.
  EXPECT_EQ(result, tls[key]);
  EXPECT_EQ(ptr, tls[key]);
#endif
}
