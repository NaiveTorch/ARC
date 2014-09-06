// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Logs progress of loading assets, classes and shared libraries.

#ifndef COMMON_LOAD_PROGRESS_LOG_H_
#define COMMON_LOAD_PROGRESS_LOG_H_

#include <string>

namespace arc {

// This class is accessed to record events related to loading an application.
// Various asset, dalvik class and shared object loading events are recorded.
class LoadProgressLogger {
 public:
  static void LogAssetEntry(const char* file, const char* entry);
  static void LogAssetEntryRead(const char* entry, int size);
  static void LogAssetEntryGetBuffer(const char* entry);
  static void LogAssetEntryOpenFd(const char* entry);
  static void LogAssetBitmapOpen(const char* entry);
  static void LogAssetBitmapBytes(const char* entry);
  static void LogAssetBitmapDraw(const char* entry);
  static void LogAssetFontOpen(const char* entry);
  static void LogAssetFontParse(const char* entry);
  static void LogSharedLibrary(const char* path);
  static void LogClassLoad(const char* descriptor);

 private:
  LoadProgressLogger() {}
  ~LoadProgressLogger() {}
};

}  // namespace arc

#endif  // COMMON_LOAD_PROGRESS_LOG_H_
