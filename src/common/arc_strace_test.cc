// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <dlfcn.h>
#include <fcntl.h>
#include <sys/mman.h>

#include "base/strings/stringprintf.h"
#include "common/arc_strace.h"
#include "gtest/gtest.h"

namespace arc {

TEST(ArcStrace, GetAccessModeStr) {
  EXPECT_EQ("R_OK|W_OK|X_OK", GetAccessModeStr(R_OK|W_OK|X_OK));
  EXPECT_EQ("F_OK", GetAccessModeStr(F_OK));
  int bad_mode = ~0 & ~R_OK & ~W_OK & ~X_OK;
  EXPECT_EQ(base::StringPrintf("%d???", bad_mode), GetAccessModeStr(bad_mode));
}

TEST(ArcStrace, GetOpenFlagStr) {
  EXPECT_EQ("O_RDONLY", GetOpenFlagStr(O_RDONLY));
  EXPECT_EQ("O_WRONLY|O_CREAT|O_EXCL|O_TRUNC",
            GetOpenFlagStr(O_WRONLY|O_CREAT|O_EXCL|O_TRUNC));
  EXPECT_EQ("O_RDWR|O_NOCTTY|O_APPEND|O_NONBLOCK|O_SYNC",
            GetOpenFlagStr(O_RDWR|O_NOCTTY|O_APPEND|O_NONBLOCK|O_SYNC));
  EXPECT_EQ("O_RDWR|O_DSYNC|O_LARGEFILE|O_PATH",
            GetOpenFlagStr(O_RDWR|O_DSYNC|O_LARGEFILE|O_PATH));
}

TEST(ArcStrace, GetDlopenFlagStr) {
  EXPECT_EQ("RTLD_LAZY|RTLD_GLOBAL",
            GetDlopenFlagStr(RTLD_LAZY|RTLD_GLOBAL));
  // In bionic, RTLD_NOW is 0, so we cannot show it.
  EXPECT_EQ("RTLD_LOCAL",
            GetDlopenFlagStr(RTLD_NOW|RTLD_LOCAL));
}

TEST(ArcStrace, GetMmapProtStr) {
  EXPECT_EQ("PROT_READ|PROT_WRITE|PROT_EXEC",
            GetMmapProtStr(PROT_READ|PROT_WRITE|PROT_EXEC));
  EXPECT_EQ("PROT_NONE", GetMmapProtStr(0));
}

TEST(ArcStrace, GetMmapFlagStr) {
  EXPECT_EQ("MAP_SHARED|MAP_ANONYMOUS",
            GetMmapFlagStr(MAP_SHARED|MAP_ANONYMOUS));
  EXPECT_EQ("MAP_PRIVATE|MAP_FIXED|MAP_FILE",
            GetMmapFlagStr(MAP_PRIVATE|MAP_FIXED|MAP_FILE));
}

TEST(ArcStrace, GetDlsymHandleStr) {
  static const uintptr_t kPtr = 0x12345678;
  EXPECT_EQ("RTLD_DEFAULT", GetDlsymHandleStr(RTLD_DEFAULT));
  EXPECT_EQ("RTLD_NEXT", GetDlsymHandleStr(RTLD_NEXT));
  EXPECT_EQ("0x12345678",  // assume 32bit pointer.
            GetDlsymHandleStr(reinterpret_cast<const void*>(kPtr)));
}

TEST(ArcStrace, GetRWBufStr) {
  std::string input;
  input = "foobar";
  EXPECT_EQ("\"foobar\"", GetRWBufStr(input.data(), input.size()));
  EXPECT_EQ("\"foob\"", GetRWBufStr(input.data(), 4));
  input = "f o\to\nb\ra\1r\xff";
  EXPECT_EQ("\"f o\\to\\nb\\ra\\1r\\377\"",
            GetRWBufStr(input.data(), input.size()));
  input = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  EXPECT_EQ("\"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef\"...",
            GetRWBufStr(input.data(), input.size()));
  input = "I said \"Hi.\"";
  EXPECT_EQ("\"I said \\\"Hi.\\\"\"",
            GetRWBufStr(input.data(), input.size()));
  input = "";
  EXPECT_EQ("\"\"", GetRWBufStr(input.data(), input.size()));
}

TEST(ArcStrace, GetMedian) {
  std::vector<int64_t> input;
  input.push_back(1);
  EXPECT_EQ(1LL, GetMedian(&input));
  input.push_back(5);
  EXPECT_EQ(3LL, GetMedian(&input));
  input.push_back(2);
  EXPECT_EQ(2LL, GetMedian(&input));
  input.push_back(3);
  EXPECT_EQ(2LL /* i.e. floor(2.5) */, GetMedian(&input));
  input.push_back(4);
  EXPECT_EQ(3LL, GetMedian(&input));

  input.clear();
  input.push_back(1);
  input.push_back(5);
  input.push_back(2);
  input.push_back(3);
  EXPECT_EQ(2LL, GetMedian(&input));

  input.clear();
  input.push_back(1);
  input.push_back(5);
  input.push_back(2);
  input.push_back(3);
  input.push_back(4);
  EXPECT_EQ(3LL, GetMedian(&input));
}

}  // namespace arc
