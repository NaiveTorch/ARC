// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/options.h"

#include <ctype.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "base/memory/singleton.h"
#include "base/strings/stringprintf.h"
#include "common/alog.h"

namespace arc {

static const int kInversePriorityCharMap[] = {
  ARC_LOG_SILENT,   // A
  ARC_LOG_SILENT,   // B
  ARC_LOG_SILENT,   // C
  ARC_LOG_DEBUG,    // D
  ARC_LOG_ERROR,    // E
  ARC_LOG_FATAL,    // F
  ARC_LOG_SILENT,   // G
  ARC_LOG_SILENT,   // H
  ARC_LOG_INFO,     // I
  ARC_LOG_SILENT,   // J
  ARC_LOG_SILENT,   // K
  ARC_LOG_SILENT,   // L
  ARC_LOG_SILENT,   // M
  ARC_LOG_SILENT,   // N
  ARC_LOG_SILENT,   // O
  ARC_LOG_SILENT,   // P
  ARC_LOG_SILENT,   // Q
  ARC_LOG_SILENT,   // R
  ARC_LOG_SILENT,   // S
  ARC_LOG_SILENT,   // T
  ARC_LOG_SILENT,   // U
  ARC_LOG_VERBOSE,  // V
  ARC_LOG_WARN,     // W
  ARC_LOG_SILENT,   // X
  ARC_LOG_SILENT,   // Y
  ARC_LOG_SILENT,   // Z
};

Options::Options() {
  Reset();
}

Options::~Options() {
}

// static
Options* Options::GetInstance() {
  return Singleton<Options, LeakySingletonTraits<Options> >::get();
}

// static
bool Options::ParseBoolean(const char* str) {
    return !strcmp(str, "true");
}

void Options::Reset() {
  app_height = 0;
  app_width = 0;
  command.clear();
  country.clear();
  dalvik_vm_lib = "libdvm.so";
  enable_adb = false;
  enable_arc_strace = false;
  enable_compositor = false;
  enable_gl_error_check = false;
  enable_mount_external_directory = false;
  fps_limit = 60;
  has_touchscreen = false;
  jdwp_port = 0;
  language.clear();
  log_load_progress = false;
  ndk_abi.clear();
  package_name.clear();
  use_play_services.clear();
  use_google_contacts_sync_adapter = false;
  user_email.clear();
  track_focus = true;
  min_stderr_log_priority_ = ARC_LOG_ERROR;
  android_density_dpi = 0;
}

inline static bool IsValidPriorityChar(char c) {
  return 'A' <= c && c <= 'Z';
}

inline int GetPriorityFromChar(char priority_char) {
  if (!IsValidPriorityChar(priority_char)) {
    return ARC_LOG_SILENT;
  } else {
    return kInversePriorityCharMap[priority_char - 'A'];
  }
}

void Options::ParseMinStderrLogPriority(const std::string& priority) {
  min_stderr_log_priority_ = GetPriorityFromChar(
      priority.length() >= 1 ? priority[0] : 0);
}

}  // namespace arc
