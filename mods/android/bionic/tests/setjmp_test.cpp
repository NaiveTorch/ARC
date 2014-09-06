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
// TODO(crbug.com/246858): Upstream this test.
//

#include <gtest/gtest.h>

#include <setjmp.h>

class SetjmpTest : public testing::Test {
 protected:
  // This inline function may change nothing, but we just make sure we
  // can go back beyond an inline function.
  inline void first_function() {
    second_function();
  }

  // To make some interesting changes for our stack, we call two
  // noinline functions. Just calling a single function should be
  // sufficient, but unwinding two functions would be more non trivial
  // than unwinding a single function.
  void second_function() __attribute__((noinline)) {
    third_function();
  }

  void third_function() __attribute__((noinline)) {
    is_third_function_called_ = true;
    longjmp(env_, 42);
  }

  jmp_buf env_;
  bool is_third_function_called_;
};

TEST_F(SetjmpTest, Basic) {
  is_third_function_called_ = false;
  volatile int stack_value = 0;
  int result = setjmp(env_);
  stack_value += result + 1;
  if (result) {
    ASSERT_EQ(42, result);
    ASSERT_EQ(44, stack_value);
    ASSERT_TRUE(is_third_function_called_);
  } else {
    ASSERT_EQ(1, stack_value);
    first_function();
    ASSERT_TRUE(false);  // Not reached.
  }
}

TEST_F(SetjmpTest, SetjmpOnly) {
  EXPECT_EQ(0, setjmp(env_));
}

#if defined(__arm__)
// Copy d#n to |var| via another VFP register ("=w"). Use the indirect copy so
// that arm-nacl correctly places a sandbox instruction for fp when accessing
// the |var|.
#define StoreVfp(n, var) \
  __asm__ __volatile__("vmov.f64 %P[out], d" #n : [out] "=w" (var))

// Set d#n to zero.
#define ZeroVfp(n) \
  __asm__ __volatile__("vsub.f64 d" #n ", d" #n ", d" #n)

// Copy lr to d#n. lr is known to be non-zero.
#define ClobberVfp(n) \
  __asm__ __volatile__("vmov d" #n ", lr, lr")

// Tests if setjmp/longjmp saves/restores callee saved VFP registers (d8-d15).
// Since it is difficult to reliably clobber these registers with C code, use
// inline assembly.
TEST_F(SetjmpTest, ArmVfpRegisters) {
  __asm__ __volatile__("vpush {d8-d15}");

  // Overwrite d8-d15 with zero.
  ZeroVfp(8);
  ZeroVfp(9);
  ZeroVfp(10);
  ZeroVfp(11);
  ZeroVfp(12);
  ZeroVfp(13);
  ZeroVfp(14);
  ZeroVfp(15);

  int result = setjmp(env_);
  if (result) {
    // Confirm that the original values (0) of d8-d15 are restored upon longjmp.
    double after;
    StoreVfp(8, after);  // copy d8 to |after|.
    EXPECT_EQ(0.0, after);
    StoreVfp(9, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(10, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(11, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(12, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(13, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(14, after);
    EXPECT_EQ(0.0, after);
    StoreVfp(15, after);
    EXPECT_EQ(0.0, after);
  } else {
    // Overwrite d8-d15 with lr.
    ClobberVfp(8);
    ClobberVfp(9);
    ClobberVfp(10);
    ClobberVfp(11);
    ClobberVfp(12);
    ClobberVfp(13);
    ClobberVfp(14);
    ClobberVfp(15);
    longjmp(env_, 1);
    ASSERT_TRUE(false);  // Not reached.
  }

  __asm__ __volatile__("vpop {d8-d15}");
}
#endif
