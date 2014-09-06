// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#ifndef COMMON_LOGD_WRITE_H_
#define COMMON_LOGD_WRITE_H_

#include <string>

namespace arc {

typedef void (*LogWriter)(const void* buf, size_t count);

// Sets a function which WriteLog() uses in order to write log messages.
void SetLogWriter(LogWriter writer);

// Writes a log message to error stream. stderr is used by default.
// The output stream can be replaced by SetLogWriter(). This is used to
// avoid to call write() or fprintf() inside irt write hook.
void WriteLog(const std::string& log);

}  // namespace arc

#endif  // COMMON_LOGD_WRITE_H_

