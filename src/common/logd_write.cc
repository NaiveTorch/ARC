// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// This file provides the low level logging functions normally in liblog.
// These functions are called directly by macros like LOG_FATAL_IF and
// ALOGV and ALOGE (defined in system/core/cutils/log.h) throughout
// the Android JNI code.  These are implemented on the Android code
// base in system/core/liblog/logd_write.c

#include "common/logd_write.h"

#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <string>

#include "base/strings/stringprintf.h"
#include "common/alog.h"
#include "common/logger.h"
#include "common/options.h"
#include "common/scoped_pthread_mutex_locker.h"
#include "common/trace_event.h"

static const char priority_char_map[] = {
  ' ',  // ANDROID_LOG_UNKNOWN
  ' ',  // ANDROID_LOG_DEFAULT
  'V',  // ANDROID_LOG_VERBOSE
  'D',  // ANDROID_LOG_DEBUG
  'I',  // ANDROID_LOG_INFO
  'W',  // ANDROID_LOG_WARN
  'E',  // ANDROID_LOG_ERROR
  'F',  // ANDROID_LOG_FATAL
  ' ',  // ANDROID_LOG_SILENT
};

const int kTagSpacing = 15;

namespace {

arc::AddCrashExtraInformationFunction g_add_crash_extra_information = NULL;
const char kLogMessage[] = "log_message";

}  // namespace

namespace arc {

namespace {

LogWriter g_log_writer;
pthread_mutex_t g_mutex = PTHREAD_MUTEX_INITIALIZER;

bool ShouldLog(arc_LogPriority priority) {
  if (priority < ARC_LOG_VERBOSE || priority >= ARC_LOG_SILENT)
    return false;
  return priority >= Options::GetInstance()->GetMinStderrLogPriority();
}

void PrintLog(int prio, const char* tag, const char* msg) {
  int tag_len = strlen(tag);
  int stored_errno = errno;
  WriteLog(base::StringPrintf("%c/%s:%*s %s\n", priority_char_map[prio], tag,
      tag_len > kTagSpacing ? 0 : kTagSpacing - tag_len, "", msg));
  errno = stored_errno;
}

}  // namespace

void RegisterCrashCallback(AddCrashExtraInformationFunction function) {
  g_add_crash_extra_information = function;
}


void SetLogWriter(LogWriter writer) {
  ScopedPthreadMutexLocker lock(&g_mutex);
  g_log_writer = writer;
}

void WriteLog(const std::string& log) {
  pthread_mutex_lock(&g_mutex);
  LogWriter log_writer = g_log_writer;
  pthread_mutex_unlock(&g_mutex);
  if (log_writer)
    log_writer(log.c_str(), log.size());
  else
    write(STDERR_FILENO, log.c_str(), log.size());
}

std::string FormatBuf(const char* fmt, va_list ap) {
  if (!fmt)
    return std::string();
  std::string buf;
  base::StringAppendV(&buf, fmt, ap);
  return buf;
}

int PrintLogBufUnchecked(int bufID, int prio, const char* tag,
                          const std::string& msg) {
  // We do not log the bufID just because it seems too verbose.
  int result = Logger::GetInstance()->Log(
      static_cast<arc_log_id_t>(bufID), prio, tag, msg.c_str());
  PrintLog(prio, tag, msg.c_str());
  return result;
}

int VPrintLogBuf(int bufID, int prio, const char* tag,
                 const char* fmt, va_list ap) {
  std::string buf;
  base::StringAppendV(&buf, fmt, ap);
  int ret = Logger::GetInstance()->Log(
      static_cast<arc_log_id_t>(bufID), prio, tag, buf.c_str());

  if (arc::ShouldLog(static_cast<arc_LogPriority>(prio))) {
    PrintLog(prio, tag, buf.c_str());
  }
  return ret;
}

int PrintLogBuf(int bufID, int prio, const char* tag, const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  VPrintLogBuf(bufID, prio, tag, fmt, arguments);
  va_end(arguments);
  return 0;
}

}  // namespace arc

extern "C"
int arc_log_buf_write_unchecked(int bufID, int prio, const char* tag,
                                  const char* msg) {
  int ret = arc::Logger::GetInstance()->Log(
      static_cast<arc_log_id_t>(bufID), prio, tag, msg);
  arc::PrintLog(prio, tag, msg);
  return ret;
}

extern "C"
int __android_log_print(int prio, const char* tag, const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  int ret = arc::VPrintLogBuf(ARC_LOG_ID_MAIN, prio, tag, fmt, arguments);
  va_end(arguments);
  return ret;
}

extern "C"
int __android_log_buf_print(int bufID, int prio, const char* tag,
    const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  int ret = arc::VPrintLogBuf(ARC_LOG_ID_MAIN, prio, tag, fmt, arguments);
  va_end(arguments);
  return ret;
}

extern "C"
int __android_log_vprint(int prio, const char* tag, const char* fmt,
                         va_list ap) {
  return arc::VPrintLogBuf(ARC_LOG_ID_MAIN, prio, tag, fmt, ap);
}

extern "C"
int __android_log_bwrite(int32_t tag, const void* payload, size_t len) {
  // 'payload' is not UTF8 and screws up the logs on ChromeOS if you try to
  // print it as a char*.
  // TODO(2013/05/14): Change "len" to "payload" and base64 or hex
  // encode the payload.
  TRACE_EVENT_INSTANT2(ARC_TRACE_CATEGORY, "EventLogTag",
                       "tag", tag,
                       "len", len);
  return arc::Logger::GetInstance()->LogEvent(tag, payload, len);
}

extern "C"
int __android_log_btwrite(int32_t tag, char type, const void* payload,
    size_t len) {
  // TODO(2013/05/14): Change "len" to "payload" and base64 or hex
  // encode the payload.
  TRACE_EVENT_INSTANT2(ARC_TRACE_CATEGORY, "EventLogTag",
                       "tag", tag,
                       "len", len);
  return arc::Logger::GetInstance()->LogEventWithType(
      tag, type, payload, len);
}

extern "C"
int __android_log_write(int prio, const char* tag, const char* msg) {
  int ret = arc::Logger::GetInstance()->Log(
      ARC_LOG_ID_MAIN, prio, tag, msg);
  if (arc::ShouldLog(arc_LogPriority(prio))) {
    arc::PrintLog(prio, tag, msg);
  }
  return ret;
}

extern "C"
int __android_log_buf_write(int bufID, int prio, const char* tag,
                            const char* msg) {
  int ret = arc::Logger::GetInstance()->Log(
      ARC_LOG_ID_MAIN, prio, tag, msg);
  if (arc::ShouldLog(arc_LogPriority(prio))) {
    arc::PrintLog(prio, tag, msg);
  }
  return ret;
}

extern "C"
void __android_log_assert(const char* cond, const char* tag,
                          const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  arc::WriteLog(base::StringPrintf("CONDITION %s WAS TRUE\n", cond));
  std::string msg = arc::FormatBuf(fmt, arguments);
  arc::PrintLogBufUnchecked(ARC_LOG_ID_MAIN,
                            ARC_LOG_FATAL,
                            tag,
                            msg);
  if (g_add_crash_extra_information != NULL)
    g_add_crash_extra_information(arc::ReportableOnlyForTesters,
                                  kLogMessage,
                                  msg.c_str());

  va_end(arguments);

  // Trap.
  abort();
}

extern "C"
void __android_log_vassert(const char* cond, const char* tag,
                           const char* fmt, va_list args) {
  arc::WriteLog(base::StringPrintf("CONDITION %s WAS TRUE\n", cond));
  std::string msg = arc::FormatBuf(fmt, args);
  arc::PrintLogBufUnchecked(ARC_LOG_ID_MAIN,
                            ARC_LOG_FATAL,
                            tag,
                            msg);
  if (g_add_crash_extra_information != NULL)
    g_add_crash_extra_information(arc::ReportableOnlyForTesters,
                                  kLogMessage,
                                  msg.c_str());

  // Trap.
  abort();
}

extern "C"
void __android_log_assert_with_source(const char* cond, const char* tag,
                                      const char* file, int line,
                                      const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  arc::WriteLog(base::StringPrintf(
      "CONDITION %s WAS TRUE AT %s:%d\n", cond, file, line));
  std::string msg = arc::FormatBuf(fmt, arguments);
  arc::PrintLogBufUnchecked(ARC_LOG_ID_MAIN,
                            ARC_LOG_FATAL,
                            tag,
                            msg);
  va_end(arguments);

  if (g_add_crash_extra_information != NULL)
    g_add_crash_extra_information(arc::ReportableOnlyForTesters,
                                  kLogMessage,
                                  msg.c_str());

  // Trap.
  abort();
}

extern "C"
void __android_log_assert_with_source_and_add_to_crash_report(
    const char* cond, const char* tag,
    const char* file, int line,
    const char* fmt, ...) {
  va_list arguments;
  va_start(arguments, fmt);
  arc::WriteLog(base::StringPrintf(
      "CONDITION %s WAS TRUE AT %s:%d\n", cond, file, line));
  std::string msg = arc::FormatBuf(fmt, arguments);
  arc::PrintLogBufUnchecked(ARC_LOG_ID_MAIN,
                            ARC_LOG_FATAL,
                            tag,
                            msg);
  va_end(arguments);

  if (g_add_crash_extra_information != NULL)
    g_add_crash_extra_information(arc::ReportableForAllUsers,
                                  kLogMessage,
                                  msg.c_str());

  // Trap.
  abort();
}
