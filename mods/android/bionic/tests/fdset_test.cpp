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

#include <sys/select.h>

TEST(fdset, Basic) {
  fd_set fds;
  // Fill all bits.
  memset(&fds, 0xff, sizeof(fds));
  for (int i = 0; i < FD_SETSIZE; i++)
    ASSERT_TRUE(FD_ISSET(i, &fds));
  FD_ZERO(&fds);
  for (int i = 0; i < FD_SETSIZE; i++)
    ASSERT_FALSE(FD_ISSET(i, &fds));
  for (int i = 0; i < FD_SETSIZE; i++) {
    FD_SET(i, &fds);
    ASSERT_TRUE(FD_ISSET(i, &fds));
  }
  for (int i = 0; i < FD_SETSIZE; i++) {
    FD_CLR(i, &fds);
    ASSERT_FALSE(FD_ISSET(i, &fds));
  }
}
