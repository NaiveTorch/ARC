// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Logs progress of loading assets, classes and shared libraries.

#include "common/load_progress_log.h"

#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>

#include "base/memory/singleton.h"
#include "base/synchronization/lock.h"
#include "common/alog.h"
#include "common/options.h"

namespace arc {

static const char* kFileName = "/storage/sdcard/arc_load_progress.log";

static const char* kPrefixAssetEntry = "ASSET_ENTRY";
static const char* kPrefixAssetEntryRead = "ASSET_ENTRY_READ";
static const char* kPrefixAssetEntryGetBuffer = "ASSET_ENTRY_GETBUFFER";
static const char* kPrefixAssetEntryOpenFd = "ASSET_ENTRY_OPENFD";
static const char* kPrefixAssetBitmapOpen = "ASSET_BITMAP_OPEN";
static const char* kPrefixAssetBitmapBytes = "ASSET_BITMAP_BYTES";
static const char* kPrefixAssetBitmapDraw = "ASSET_BITMAP_DRAW";
static const char* kPrefixAssetFontOpen = "ASSET_FONT_OPEN";
static const char* kPrefixAssetFontParse = "ASSET_FONT_PARSE";
static const char* kPrefixSharedLibrary = "SHARED_LIBRARY";
static const char* kPrefixClassLoad = "CLASS_LOAD";

class LoggerData {
 public:
  static LoggerData* GetInstance();

  int GetTimestampForLog() const;
  int GetLogFile() const { return log_file_; }
  base::Lock& GetMutex() { return mu_; }

  char tmp_storage_[2048];

 private:
  LoggerData();
  ~LoggerData() {}

  static int64_t GetCurrentTime();

  int64_t base_time_;
  int log_file_;
  base::Lock mu_;

  friend struct DefaultSingletonTraits<LoggerData>;
};

LoggerData* LoggerData::GetInstance() {
  return Singleton<LoggerData, LeakySingletonTraits<LoggerData> >::get();
}

LoggerData::LoggerData() : base_time_(GetCurrentTime()) {
  if (Options::GetInstance()->log_load_progress) {
    log_file_ = open(kFileName, O_CREAT | O_WRONLY | O_TRUNC, 0x640);
    if (log_file_ != -1) {
      ALOGW("Opened load progress log file: %s", kFileName);
    } else {
      ALOGE("Unable to open for writing: %s", kFileName);
    }
  } else {
    log_file_ = -1;
  }
}

int LoggerData::GetTimestampForLog() const {
  return static_cast<int>(GetCurrentTime() - base_time_);
}

int64_t LoggerData::GetCurrentTime() {
  struct timeval now;
  gettimeofday(&now, NULL);
  return now.tv_sec * 1000000LL + now.tv_usec;
}

#define LOG_ENTRY(prefix, fmt, ...) \
    LoggerData* logger = LoggerData::GetInstance(); \
    int log_file = logger->GetLogFile(); \
    if (log_file != -1) { \
      base::AutoLock lock(logger->GetMutex()); \
      int time = logger->GetTimestampForLog(); \
      int len = snprintf(logger->tmp_storage_, \
          sizeof(LoggerData::tmp_storage_), \
          "%s[%d]:" fmt "\n", prefix, time, ##__VA_ARGS__); \
      write(log_file, logger->tmp_storage_, len); \
    }

void LoadProgressLogger::LogAssetEntry(const char* file, const char* entry) {
  LOG_ENTRY(kPrefixAssetEntry, "%s\t%s", file, entry);
}

void LoadProgressLogger::LogAssetEntryRead(const char* entry, int size) {
  LOG_ENTRY(kPrefixAssetEntryRead, "%s\t%d", entry, size);
}

void LoadProgressLogger::LogAssetEntryGetBuffer(const char* entry) {
  LOG_ENTRY(kPrefixAssetEntryGetBuffer, "%s", entry);
}

void LoadProgressLogger::LogAssetEntryOpenFd(const char* entry) {
  LOG_ENTRY(kPrefixAssetEntryOpenFd, "%s", entry);
}

void LoadProgressLogger::LogAssetBitmapOpen(const char* entry) {
  LOG_ENTRY(kPrefixAssetBitmapOpen, "%s", entry);
}

void LoadProgressLogger::LogAssetBitmapBytes(const char* entry) {
  LOG_ENTRY(kPrefixAssetBitmapBytes, "%s", entry);
}

void LoadProgressLogger::LogAssetBitmapDraw(const char* entry) {
  LOG_ENTRY(kPrefixAssetBitmapDraw, "%s", entry);
}

void LoadProgressLogger::LogAssetFontOpen(const char* entry) {
  LOG_ENTRY(kPrefixAssetFontOpen, "assets/%s", entry);
}

void LoadProgressLogger::LogAssetFontParse(const char* entry) {
  LOG_ENTRY(kPrefixAssetFontParse, "assets/%s", entry);
}

void LoadProgressLogger::LogSharedLibrary(const char* path) {
  LOG_ENTRY(kPrefixSharedLibrary, "%s", path);
}

void LoadProgressLogger::LogClassLoad(const char* descriptor) {
  LOG_ENTRY(kPrefixClassLoad, "%s", descriptor);
}

}  // namespace arc
