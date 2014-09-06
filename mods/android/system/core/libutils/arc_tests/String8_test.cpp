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
// TODO(crbug.com/370682): Move this into libutils/tests/String8_test.cpp once
// we can build and run them.

#include <utils/String8.h>

#include "gtest/gtest.h"

// Tests android::String8 which we patched.
TEST(ModsTest, TestAndroidString8) {
    EXPECT_STREQ("12345X", android::String8::format("%dX", 12345).string());
}
