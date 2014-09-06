// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/options.h"
#include "gtest/gtest.h"

int main(int argc, char **argv) {
  ::testing::InitGoogleTest(&argc, argv);

  // Set logging verbosity for unit testing.
  arc::Options::GetInstance()->ParseMinStderrLogPriority("W");

  return RUN_ALL_TESTS();
}
