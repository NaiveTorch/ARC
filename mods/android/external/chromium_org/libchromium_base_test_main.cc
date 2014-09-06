// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "base/at_exit.h"
#include "gtest/gtest.h"

// To run tests in chromium-ppapi/base/, we need to override main. In
// chromium, base/test/test_suite.cc does that, but it is difficult to
// compile test_suite.cc for ARC. This is simplified version of the main
// function.
int main(int argc, char** argv) {
  // Some tests in chromium-ppapi/base/ depend on AtExitManager.
  base::AtExitManager manager;
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
