// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include "bare_metal/common/irt_futex.h"
#include "bionic/libc/arch-nacl/syscalls/nacl_timespec.h"
#include "gtest/gtest.h"

namespace bare_metal {

class IrtFutexTest : public testing::Test {
};

TEST_F(IrtFutexTest, ConvertNaClAbsTimeToRelTime) {
  struct nacl_abi_timespec abs;
  struct timespec cur;
  struct timespec rel;

  abs.tv_sec = 43;
  abs.tv_nsec = 99;
  cur.tv_sec = 42;
  cur.tv_nsec = 50;
  ConvertNaClAbsTimeToRelTime(&abs, &cur, &rel);
  EXPECT_EQ(1, rel.tv_sec);
  EXPECT_EQ(49, rel.tv_nsec);

  abs.tv_sec = 50;
  abs.tv_nsec = 1;
  cur.tv_sec = 40;
  cur.tv_nsec = 999999999;
  ConvertNaClAbsTimeToRelTime(&abs, &cur, &rel);
  EXPECT_EQ(9, rel.tv_sec);
  EXPECT_EQ(2, rel.tv_nsec);

  // Return zero for a negative relative time.
  abs.tv_sec = 9;
  abs.tv_nsec = 10;
  cur.tv_sec = 10;
  cur.tv_nsec = 10;
  ConvertNaClAbsTimeToRelTime(&abs, &cur, &rel);
  EXPECT_EQ(0, rel.tv_sec);
  EXPECT_EQ(0, rel.tv_nsec);

  abs.tv_sec = 10;
  abs.tv_nsec = 9;
  cur.tv_sec = 10;
  cur.tv_nsec = 10;
  ConvertNaClAbsTimeToRelTime(&abs, &cur, &rel);
  EXPECT_EQ(0, rel.tv_sec);
  EXPECT_EQ(0, rel.tv_nsec);
}

}  // namespace bare_metal
