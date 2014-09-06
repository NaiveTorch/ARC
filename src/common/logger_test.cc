// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Tests for logging functionality.

#include "common/logger.h"
#include "common/options.h"
#include "gtest/gtest.h"

namespace arc {

TEST(LoggerTest, General) {
  Logger* logger = Logger::GetInstance();
  LoggerReader* reader = logger->CreateReader(ARC_LOG_ID_MAIN);
  logger->FlushBuffer(reader);
  EXPECT_FALSE(logger->IsReadReady(reader));

  EXPECT_EQ(1024U * 64U, logger->GetBufferSize(reader));
  EXPECT_EQ(0U, logger->GetLogLength(reader));
  EXPECT_EQ(0U, logger->GetNextEntryLength(reader));

  char tag[] = "Test";
  char msg[] = "Test log";
  logger->Log(ARC_LOG_ID_MAIN, ARC_LOG_DEBUG, tag, msg);
  EXPECT_TRUE(logger->IsReadReady(reader));
  const size_t kPayloadSize = 1 + sizeof(tag) + sizeof(msg);
  const size_t kEntrySize = kPayloadSize + sizeof(struct logger_entry);

  EXPECT_EQ(kEntrySize, logger->GetLogLength(reader));
  EXPECT_EQ(kEntrySize, logger->GetNextEntryLength(reader));

  char buf[4096];
  struct logger_entry* entry = reinterpret_cast<struct logger_entry*>(buf);
  ssize_t retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
  EXPECT_EQ(kEntrySize, static_cast<size_t>(retval));

  EXPECT_EQ(entry->msg[0], ARC_LOG_DEBUG);
  EXPECT_STREQ(tag, entry->msg + 1);
  EXPECT_STREQ(msg, entry->msg + 1 + sizeof(tag));

  EXPECT_EQ(0U, logger->GetLogLength(reader));
  EXPECT_EQ(0U, logger->GetNextEntryLength(reader));
  logger->ReleaseReader(reader);

  reader = logger->CreateReader(ARC_LOG_ID_MAIN);

  logger->Log(ARC_LOG_ID_MAIN, ARC_LOG_DEBUG, tag, msg);

  EXPECT_TRUE(logger->IsReadReady(reader));
  EXPECT_EQ(kEntrySize * 2, logger->GetLogLength(reader));
  EXPECT_EQ(kEntrySize, logger->GetNextEntryLength(reader));

  retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
  EXPECT_EQ(kEntrySize, static_cast<size_t>(retval));
  EXPECT_EQ(kPayloadSize, entry->len);

  EXPECT_EQ(kEntrySize, logger->GetLogLength(reader));
  EXPECT_EQ(kEntrySize, logger->GetNextEntryLength(reader));

  retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
  EXPECT_EQ(kEntrySize, static_cast<size_t>(retval));
  EXPECT_EQ(kPayloadSize, entry->len);

  EXPECT_EQ(0U, logger->GetLogLength(reader));
  EXPECT_EQ(0U, logger->GetNextEntryLength(reader));

  EXPECT_EQ(entry->msg[0], ARC_LOG_DEBUG);
  EXPECT_STREQ(tag, entry->msg + 1);
  EXPECT_STREQ(msg, entry->msg + 1 + sizeof(tag));

  logger->FlushBuffer(reader);
  EXPECT_EQ(0U, logger->GetLogLength(reader));
  EXPECT_EQ(0U, logger->GetNextEntryLength(reader));

  logger->ReleaseReader(reader);
}


TEST(LoggerTest, OverWrite) {
  const int kBufferSize = 1024 * 64;
  const int kTotalWriteSize = kBufferSize * 39;
  Logger* logger = Logger::GetInstance();

  char tag[] = "Test";
  char msg[] = "Message xxxxx";

  const size_t kPayloadSize = 1 + sizeof(tag) + sizeof(msg);
  const size_t kEntrySize = kPayloadSize + sizeof(struct logger_entry);
  const int kCount = (kTotalWriteSize - 2)  /  kEntrySize;

  int i;
  for (i = 0; i < kCount; i++) {
    snprintf(msg, sizeof(msg), "Message %05d", i);
    logger->Log(ARC_LOG_ID_MAIN, ARC_LOG_DEBUG, tag, msg);
  }

  LoggerReader* reader = logger->CreateReader(ARC_LOG_ID_MAIN);

  EXPECT_TRUE(logger->IsReadReady(reader));
  size_t log_length = (kBufferSize - 2) / kEntrySize * kEntrySize;

  EXPECT_EQ(log_length, logger->GetLogLength(reader));

  char buf[4096];
  struct logger_entry* entry = reinterpret_cast<struct logger_entry*>(buf);

  int n = kCount - log_length / kEntrySize;
  while (logger->IsReadReady(reader)) {
    EXPECT_EQ(log_length, logger->GetLogLength(reader));

    ssize_t retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
    EXPECT_EQ(kEntrySize, static_cast<size_t>(retval));

    snprintf(msg, sizeof(msg), "Message %05d", n);
    EXPECT_EQ(entry->msg[0], ARC_LOG_DEBUG);
    EXPECT_STREQ(tag, entry->msg + 1);
    EXPECT_STREQ(msg, entry->msg + 1 + sizeof(tag));
    log_length -= retval;
    n++;
  }

  EXPECT_EQ(i, n);

  logger->ReleaseReader(reader);
}

TEST(LoggerTest, LogEvent) {
  Logger* logger = Logger::GetInstance();
  LoggerReader* reader = logger->CreateReader(ARC_LOG_ID_EVENTS);
  logger->FlushBuffer(reader);

  EXPECT_FALSE(logger->IsReadReady(reader));

  const int32_t kTag = 3366;
  const char kPayload[] = "Event Payload";
  const size_t kEntrySize =
    sizeof(int32_t) + sizeof(kPayload) + sizeof(struct logger_entry);

  logger->LogEvent(kTag, kPayload, sizeof(kPayload));
  EXPECT_TRUE(logger->IsReadReady(reader));

  logger->LogEventWithType(kTag + 1, 'S', kPayload, sizeof(kPayload));
  EXPECT_TRUE(logger->IsReadReady(reader));

  char buf[4096];
  struct logger_entry* entry = reinterpret_cast<struct logger_entry*>(buf);

  ssize_t retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
  EXPECT_EQ(kEntrySize, static_cast<size_t>(retval));
  EXPECT_EQ(kTag, *reinterpret_cast<int32_t*>(&entry->msg[0]));
  EXPECT_STREQ(kPayload, &entry->msg[sizeof(int32_t)]);

  retval = logger->ReadLogEntry(reader, entry, sizeof(buf));
  EXPECT_EQ(kEntrySize + 1, static_cast<size_t>(retval));
  EXPECT_EQ(kTag + 1, *reinterpret_cast<int32_t*>(entry->msg));
  EXPECT_EQ('S', entry->msg[sizeof(int32_t)]);
  EXPECT_STREQ(kPayload, &entry->msg[sizeof(int32_t) + 1]);

  logger->ReleaseReader(reader);
}

}  // namespace arc

