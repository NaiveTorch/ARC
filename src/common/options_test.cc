// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Test android log filtering

#include "common/alog.h"
#include "common/options.h"
#include "gtest/gtest.h"

namespace arc {

/* For reference:
 * enum  {
 *   ANDROID_LOG_UNKNOWN = 0,
 *   ANDROID_LOG_DEFAULT,
 *
 *   ANDROID_LOG_VERBOSE,
 *   ANDROID_LOG_DEBUG,
 *   ANDROID_LOG_INFO,
 *   ANDROID_LOG_WARN,
 *   ANDROID_LOG_ERROR,
 *   ANDROID_LOG_FATAL,
 *
 *   ANDROID_LOG_SILENT,
 * };
 */


TEST(OptionsTest, ParseMinStderrLogPriority) {
  Options* options = Options::GetInstance();
  options->ParseMinStderrLogPriority("V");
  ASSERT_EQ(ARC_LOG_VERBOSE, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("D");
  ASSERT_EQ(ARC_LOG_DEBUG, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("I");
  ASSERT_EQ(ARC_LOG_INFO, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("W");
  ASSERT_EQ(ARC_LOG_WARN, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("E");
  ASSERT_EQ(ARC_LOG_ERROR, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("F");
  ASSERT_EQ(ARC_LOG_FATAL, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("S");
  ASSERT_EQ(ARC_LOG_SILENT, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("V");
  ASSERT_EQ(ARC_LOG_VERBOSE, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("");
  ASSERT_EQ(ARC_LOG_SILENT, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("DE");
  ASSERT_EQ(ARC_LOG_DEBUG, options->GetMinStderrLogPriority());

  options->ParseMinStderrLogPriority("ED");
  ASSERT_EQ(ARC_LOG_ERROR, options->GetMinStderrLogPriority());
}

}  // namespace arc
