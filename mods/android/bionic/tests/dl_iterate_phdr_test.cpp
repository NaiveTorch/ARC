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

#include <dlfcn.h>
#include <link.h>
#include <math.h>
#include <set>
#include <string>
#include <vector>

#include <gtest/gtest.h>

static int walk_phdr(struct dl_phdr_info* info, size_t size, void* data) {
  static_cast<std::vector<struct dl_phdr_info*>*>(data)->push_back(
      new struct dl_phdr_info(*info));
  return 0;
}

TEST(dl_iterate_phdr, Basic) {
  // Recent linker does not create DT_NEEDED for libm.so in
  // bionic_test if bionic_tests does not call any math functions,
  // even if -lm is specified in the command line. So, we call sqrt
  // here to make sure bionic_test is linked against libm.so.
  EXPECT_EQ(3.0, sqrt(9.0));

  std::vector<struct dl_phdr_info*> infos;
  ASSERT_EQ(0, dl_iterate_phdr(&walk_phdr, static_cast<void*>(&infos)));

  // We should have the following entries:
  //
  // 1. The dummy entry for libdl.
  // 2. The main binary.
  // 3. libc.so
  // 4. libm.so
  // 5. libstlport.so
  // 6. (On ARM with debug enabled) libc_malloc_debug_leak.so
  size_t num_infos = infos.size();
  ASSERT_LE(5UL, num_infos);

  EXPECT_FALSE(infos[0]->dlpi_addr);
  EXPECT_FALSE(infos[0]->dlpi_name);
  EXPECT_EQ(0, infos[0]->dlpi_phnum);
  // TODO(crbug.com/323864): Remove the path for __native_client__
  // once the issue has been fixed.
#if defined(__native_client__)
  EXPECT_FALSE(infos[1]->dlpi_addr);
#else
  EXPECT_TRUE(infos[1]->dlpi_addr);
#endif
  ASSERT_TRUE(infos[1]->dlpi_name);
  EXPECT_NE(0, infos[1]->dlpi_phnum);
  EXPECT_TRUE(infos[2]->dlpi_addr);
  ASSERT_TRUE(infos[2]->dlpi_name);
  EXPECT_STREQ("libc.so", infos[2]->dlpi_name);
  EXPECT_NE(0, infos[2]->dlpi_phnum);
  EXPECT_TRUE(infos[3]->dlpi_addr);
  ASSERT_TRUE(infos[3]->dlpi_name);
  EXPECT_STREQ("libm.so", infos[3]->dlpi_name);
  EXPECT_NE(0, infos[3]->dlpi_phnum);
  EXPECT_TRUE(infos[4]->dlpi_addr);
  ASSERT_TRUE(infos[4]->dlpi_name);
  EXPECT_STREQ("libstlport.so", infos[4]->dlpi_name);
  EXPECT_NE(0, infos[4]->dlpi_phnum);

  // Note about libc_malloc_debug_leak.so:
  // Even though bionic_test tries to dlopen libc_malloc_debug_leak.so
  // (when NDEBUG is not defined), it fails because unlike the real
  // arc.nexe, bionic_test does not have some symbols the DSO refers,
  // such as _Unwind_GetIP except on ARM. When dlopen fails, it (of
  // course) does not add a dl_phdr_info to the |solist|.
  // See soinfo_free() call in find_library_internal().

  for (size_t i = 0; i < infos.size(); i++)
    delete infos[i];
}
