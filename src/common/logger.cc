// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/logger.h"

#include <errno.h>
#include <stdio.h>
#include <sys/syscall.h>

#include <algorithm>
#include <list>

#include "base/bind.h"
#include "base/callback.h"
#include "base/memory/singleton.h"
#include "base/synchronization/lock.h"

namespace arc {

namespace {

const int kLoggerBufferSize = 1024 * 64;
const int kEventLoggerBufferSize = 1024 * 256;

}  // namespace

class LoggerReader {
 public:
  LoggerBuffer* buffer() { return buffer_; }

 private:
  friend class LoggerBuffer;

  explicit LoggerReader(LoggerBuffer* buffer);
  ~LoggerReader();

  LoggerBuffer* buffer_;

  base::Callback<void(void)> ready_callback_;

  size_t offset_;
};

struct IOVec {
  const void* base;
  size_t len;
};

class LoggerBuffer {
 public:
  explicit LoggerBuffer(size_t size);

  size_t Truncate(size_t offset) { return offset & (size_ - 1); }

  LoggerReader* CreateReader();

  void ReleaseReader(LoggerReader* reader);

  size_t WriteLog(int prio, const char* tag, const char* msg);

  size_t WriteEventLog(int32_t tag, const void* payload, size_t len);

  size_t WriteEventLogWithType(int32_t tag, char type, const void* payload,
      size_t len);

  ssize_t ReadLogEntry(LoggerReader* reader,
                       struct logger_entry* entry,
                       size_t len);

  // Return true if the reader is read ready.
  bool IsReadReady(LoggerReader* reader);

  void WaitForReadReady(LoggerReader* reader,
                        const base::Callback<void(void)>& callback);

  size_t GetLogLength(LoggerReader* reader);

  size_t GetNextLogEntryLength(LoggerReader* reader);

  void Flush();

  size_t size() { return size_; }

 private:
  void ReadLocked(void* buf, size_t offset, size_t count);

  ssize_t ReadLogLocked(LoggerReader* reader,
                        struct logger_entry* entry,
                        size_t len);

  size_t WriteV(const struct IOVec* iovec, int count);

  size_t WriteLocked(const void* buf, size_t count);

  // Write two zero bytes to indicate the end of the buffer.
  void WriteEOBLocked();

  // Get the logger entry header at the given offset.
  const struct logger_entry* GetEntryHeader(size_t offset,
                                            struct logger_entry* scratch);
  const struct logger_entry* GetEntryHeaderLocked(size_t offset,
                                                  struct logger_entry* scratch);

  // Get the logger message length at the given offset.
  size_t GetEntryMsgLenLocked(size_t offset);

  // Get the next logger enter offset after offset + len.
  size_t GetNextEntryLocked(size_t offset, size_t len);

  bool IsBetween(size_t a, size_t b, size_t c);

  // Force readers to advcance if the logger entry at the current offset is
  // going to be over written.
  void ForceReadersToAdvanceLocked(size_t len);

  bool IsReadReadyLocked(LoggerReader* reader);

 private:
  base::Lock lock_;

  size_t size_;

  scoped_ptr<char[]> buffer_;

  // write offset for new logger entry. note: 0 <= write_offset_ < size_
  size_t write_offset_;

  // Initial read offset for new readers. note: 0 <= head_offset_ < size_
  size_t head_offset_;

  std::list<LoggerReader*> readers_;
};

LoggerReader::LoggerReader(LoggerBuffer* buffer)
    : buffer_(buffer) {
}

LoggerReader::~LoggerReader() {
}

LoggerBuffer::LoggerBuffer(size_t size)
  : size_(size),
    buffer_(new char[size]),
    write_offset_(0),
    head_offset_(0) {
  assert((size & (size -1)) == 0);
  assert(LOGGER_ENTRY_MAX_PAYLOAD < size);
  WriteEOBLocked();
}

LoggerReader* LoggerBuffer::CreateReader() {
  base::AutoLock locker(lock_);
  LoggerReader* reader = new LoggerReader(this);
  readers_.push_back(reader);
  reader->offset_ = head_offset_;
  return reader;
}

void LoggerBuffer::ReleaseReader(LoggerReader* reader) {
  base::AutoLock locker(lock_);
  readers_.remove(reader);
  delete reader;
}

void LoggerBuffer::ReadLocked(void* buf, size_t offset, size_t count) {
  char* p = static_cast<char*>(buf);
  while (count) {
    size_t n = std::min(count, size_ - offset);
    memcpy(p, buffer_.get() + offset, n);
    p += n;
    count -= n;
    offset = Truncate(offset + n);
  }
}

size_t LoggerBuffer::WriteLocked(const void* buf, size_t count) {
  const char *p = static_cast<const char*>(buf);
  while (count) {
    size_t n = std::min(count, size_ - write_offset_);
    memcpy(buffer_.get() + write_offset_, p, n);
    write_offset_ = Truncate(write_offset_ + n);
    p += n;
    count -= n;
  }
  return p - static_cast<const char*>(buf);
}

void LoggerBuffer::WriteEOBLocked() {
  buffer_[write_offset_] = 0;
  buffer_[Truncate(write_offset_ + 1)] = 0;
}

const struct logger_entry* LoggerBuffer::GetEntryHeader(
    size_t offset, struct logger_entry* scratch) {
  base::AutoLock locker(lock_);
  return GetEntryHeaderLocked(offset, scratch);
}

const struct logger_entry* LoggerBuffer::GetEntryHeaderLocked(
    size_t offset, struct logger_entry* scratch) {
  size_t len = std::min(sizeof(struct logger_entry), size_ - offset);
  if (len == sizeof(struct logger_entry)) {
    return static_cast<const struct logger_entry*>(static_cast<void*>(
          buffer_.get() + offset));
  }

  ReadLocked(scratch, offset, sizeof(struct logger_entry));
  return scratch;
}

size_t LoggerBuffer::GetEntryMsgLenLocked(size_t offset) {
  struct logger_entry scratch;
  const struct logger_entry* header = GetEntryHeaderLocked(offset, &scratch);
  return header->len;
}

size_t LoggerBuffer::GetNextEntryLocked(size_t offset, size_t len) {
  size_t count = 0;
  do {
    size_t n = sizeof(struct logger_entry) + GetEntryMsgLenLocked(offset);
    offset = Truncate(offset + n);
    count += n;
  } while (count < len);
  return offset;
}

// Is a < c < b, accounting for wrapping of a, b, and c positions in the buffer?
//
// That is, if a<b, check for c between a and b
// and if a>b, check for c outside (not between) a and b
//
// |------- a xxxxxxxx b --------|
//               c^
//
// |xxxxx b --------- a xxxxxxxxx|
//    c^
// or                    c^
bool LoggerBuffer::IsBetween(size_t a, size_t b, size_t c) {
  if (a < b) {
    if (a < c && c <= b)
      return true;
  } else {
    if (c <= b || a < c)
      return true;
  }
  return false;
}

void LoggerBuffer::ForceReadersToAdvanceLocked(size_t len) {
  // Is the logger empty?
  if (GetEntryMsgLenLocked(head_offset_) == 0)
    return;

  size_t woff_old = write_offset_;
  size_t woff_new_plus_2 = Truncate(write_offset_ + len + 2);
  if (IsBetween(woff_old, woff_new_plus_2, head_offset_)) {
    head_offset_ = GetNextEntryLocked(head_offset_,
        Truncate(woff_new_plus_2 + size_ - head_offset_));
  }

  std::list<LoggerReader*>::iterator it = readers_.begin();
  std::list<LoggerReader*>::const_iterator last = readers_.end();

  while (it != last) {
    if (GetEntryMsgLenLocked((*it)->offset_) != 0 &&
        IsBetween(woff_old, woff_new_plus_2, (*it)->offset_)) {
      (*it)->offset_ = head_offset_;
    }
    it++;
  }
}

bool LoggerBuffer::IsReadReadyLocked(LoggerReader* reader) {
  return GetEntryMsgLenLocked(reader->offset_);
}

size_t LoggerBuffer::WriteV(const struct IOVec* iovec, int count) {
  size_t len = 0;
  int i;
  for (i = 0; i < count; i++) {
    len += iovec[i].len;
  }

  if (len == 0)
    return 0;

  struct logger_entry header;
  struct timespec now;

  len = std::min(len, static_cast<size_t>(LOGGER_ENTRY_MAX_PAYLOAD));
  clock_gettime(CLOCK_MONOTONIC, &now);
  header.len = len;
  header.__pad = 0;
  header.pid = getpid();
  header.tid = gettid();
  header.sec = now.tv_sec;
  header.nsec = now.tv_nsec;

  base::AutoLock locker(lock_);
  ForceReadersToAdvanceLocked(header.len + sizeof(header));

  WriteLocked(&header, sizeof(header));
  size_t ret = len;
  for (i = 0; i < count && len > 0; i++) {
    len -= WriteLocked(iovec[i].base, std::min(iovec[i].len, len));
  }
  WriteEOBLocked();

  std::list<LoggerReader*>::iterator it = readers_.begin();
  std::list<LoggerReader*>::const_iterator last = readers_.end();
  while (it != last) {
    LoggerReader* reader = *(it++);
    if (reader->ready_callback_.is_null())
      continue;
    reader->ready_callback_.Run();
    reader->ready_callback_.Reset();
  }
  return ret;
}

size_t LoggerBuffer::WriteLog(int prio, const char* tag, const char* msg) {
  unsigned char c = static_cast<unsigned char>(prio);
  if (!tag)
    tag = "";
  struct IOVec iovec[3];
  iovec[0].base = &c;
  iovec[0].len = sizeof(c);
  iovec[1].base = tag;
  iovec[1].len = strlen(tag) + 1;
  iovec[2].base = msg;
  iovec[2].len = strlen(msg) + 1;
  return WriteV(iovec, 3);
}

size_t LoggerBuffer::WriteEventLog(
    int32_t tag, const void* payload, size_t len) {
  struct IOVec iovec[2];
  iovec[0].base = &tag;
  iovec[0].len = sizeof(tag);
  iovec[1].base = payload;
  iovec[1].len = len;
  return WriteV(iovec, 2);
}

size_t LoggerBuffer::WriteEventLogWithType(int32_t tag, char type,
    const void* payload, size_t len) {
  struct IOVec iovec[3];
  iovec[0].base = &tag;
  iovec[0].len = sizeof(tag);
  iovec[1].base = &type;
  iovec[1].len = sizeof(type);
  iovec[2].base = payload;
  iovec[2].len = len;
  return WriteV(iovec, 3);
}

ssize_t LoggerBuffer::ReadLogEntry(
    LoggerReader* reader,
    struct logger_entry* entry,
    size_t len) {
  base::AutoLock locker(lock_);
  if (!reader->ready_callback_.is_null())
    return -EBUSY;
  return ReadLogLocked(reader, entry, len);
}

bool LoggerBuffer::IsReadReady(LoggerReader* reader) {
  base::AutoLock locker(lock_);
  return IsReadReadyLocked(reader);
}

void LoggerBuffer::WaitForReadReady(LoggerReader* reader,
    const base::Callback<void()>& callback) {
  base::AutoLock locker(lock_);
  reader->ready_callback_ = callback;
}

size_t LoggerBuffer::GetLogLength(LoggerReader* reader) {
  base::AutoLock locker(lock_);
  if (!IsReadReadyLocked(reader))
    return 0;
  return Truncate(size_ - reader->offset_ + write_offset_);
}

size_t LoggerBuffer::GetNextLogEntryLength(LoggerReader* reader) {
  base::AutoLock locker(lock_);
  ssize_t len = GetEntryMsgLenLocked(reader->offset_);
  return len ? len + sizeof(struct logger_entry) : 0;
}

void LoggerBuffer::Flush() {
  base::AutoLock locker(lock_);
  write_offset_ = 0;
  head_offset_ = 0;
  WriteEOBLocked();
  std::list<LoggerReader*>::iterator it = readers_.begin();
  std::list<LoggerReader*>::const_iterator last = readers_.end();
  while (it != last) {
    LoggerReader* reader = *(it++);
    reader->offset_ = 0;
  }
}

ssize_t LoggerBuffer::ReadLogLocked(
    LoggerReader* reader, struct logger_entry* entry, size_t len) {
  if (!IsReadReadyLocked(reader))
    return -EAGAIN;

  struct logger_entry scratch;
  const struct logger_entry* header =
    GetEntryHeaderLocked(reader->offset_, &scratch);
  size_t entry_len = header->len + sizeof(struct logger_entry);
  if (len < entry_len)
    return -EINVAL;
  ReadLocked(entry, reader->offset_, entry_len);
  reader->offset_ = Truncate(reader->offset_ + entry_len);
  return entry_len;
}

// Logger class
Logger::Logger() {
  buffers_[ARC_LOG_ID_MAIN] = new LoggerBuffer(kLoggerBufferSize);
  buffers_[ARC_LOG_ID_RADIO] = new LoggerBuffer(kLoggerBufferSize);
  buffers_[ARC_LOG_ID_EVENTS] =  new LoggerBuffer(kEventLoggerBufferSize);
  buffers_[ARC_LOG_ID_SYSTEM] =  new LoggerBuffer(kLoggerBufferSize);
}

Logger::~Logger() {
  for (size_t i = 0; i < ARC_LOG_ID_MAX; ++i)
    delete buffers_[i];
}

int Logger::Log(
    arc_log_id_t log_id, int prio, const char* tag, const char* msg) {
  if (log_id < 0 || log_id >= ARC_LOG_ID_MAX)
    return -1;
  return buffers_[log_id]->WriteLog(prio, tag, msg);
}

int Logger::LogEvent(int32_t tag, const void* payload, size_t len) {
  return buffers_[ARC_LOG_ID_EVENTS]->WriteEventLog(tag, payload, len);
}

int Logger::LogEventWithType(int32_t tag, char type, const void* payload,
    size_t len) {
  return buffers_[ARC_LOG_ID_EVENTS]->WriteEventLogWithType(
      tag, type, payload, len);
}

LoggerReader* Logger::CreateReader(arc_log_id_t log_id) {
  if (log_id < 0 || log_id >= ARC_LOG_ID_MAX)
    return NULL;
  return buffers_[log_id]->CreateReader();
}

void Logger::ReleaseReader(LoggerReader* reader) {
  reader->buffer()->ReleaseReader(reader);
}

ssize_t Logger::ReadLogEntry(LoggerReader* reader, struct logger_entry* entry,
    size_t len) {
  return reader->buffer()->ReadLogEntry(reader, entry, len);
}

bool Logger::IsReadReady(LoggerReader* reader) {
  return reader->buffer()->IsReadReady(reader);
}

void Logger::WaitForReadReady(LoggerReader* reader, void (*callback)()) {
  return reader->buffer()->WaitForReadReady(reader, base::Bind(callback));
}

size_t Logger::GetBufferSize(LoggerReader* reader) {
  return reader->buffer()->size();
}

size_t Logger::GetLogLength(LoggerReader* reader) {
  return reader->buffer()->GetLogLength(reader);
}

size_t Logger::GetNextEntryLength(LoggerReader* reader) {
  return reader->buffer()->GetNextLogEntryLength(reader);
}

void Logger::FlushBuffer(LoggerReader* reader) {
  reader->buffer()->Flush();
}

Logger* Logger::GetInstance() {
  return Singleton<Logger, LeakySingletonTraits<Logger> >::get();
}

}  // namespace arc
