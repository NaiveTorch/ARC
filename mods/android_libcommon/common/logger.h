/* ARC MOD TRACK "third_party/android/system/core/include/log/logger.h" */
/* utils/logger.h
** 
** Copyright 2007, The Android Open Source Project
**
** This file is dual licensed.  It may be redistributed and/or modified
** under the terms of the Apache 2.0 License OR version 2 of the GNU
** General Public License.
*/

/* ARC MOD BEGIN */
// Copied all structures and defines from android upstream and add
// Logger class.
#ifndef COMMON_LOGGER_H_
#define COMMON_LOGGER_H_
/* ARC MOD END */

#include <stdint.h>

/*
 * The userspace structure for version 1 of the logger_entry ABI.
 * This structure is returned to userspace by the kernel logger
 * driver unless an upgrade to a newer ABI version is requested.
 */
struct logger_entry {
    uint16_t    len;    /* length of the payload */
    uint16_t    __pad;  /* no matter what, we get 2 bytes of padding */
    int32_t     pid;    /* generating process's pid */
    int32_t     tid;    /* generating process's tid */
    int32_t     sec;    /* seconds since Epoch */
    int32_t     nsec;   /* nanoseconds */
    char        msg[0]; /* the entry's payload */
};

/*
 * The userspace structure for version 2 of the logger_entry ABI.
 * This structure is returned to userspace if ioctl(LOGGER_SET_VERSION)
 * is called with version==2
 */
struct logger_entry_v2 {
    uint16_t    len;       /* length of the payload */
    uint16_t    hdr_size;  /* sizeof(struct logger_entry_v2) */
    int32_t     pid;       /* generating process's pid */
    int32_t     tid;       /* generating process's tid */
    int32_t     sec;       /* seconds since Epoch */
    int32_t     nsec;      /* nanoseconds */
    uint32_t    euid;      /* effective UID of logger */
    char        msg[0];    /* the entry's payload */
};

#define LOGGER_LOG_MAIN		"log/main"
#define LOGGER_LOG_RADIO	"log/radio"
#define LOGGER_LOG_EVENTS	"log/events"
#define LOGGER_LOG_SYSTEM	"log/system"

/*
 * The maximum size of the log entry payload that can be
 * written to the kernel logger driver. An attempt to write
 * ARC MOD BEGIN
 * more than this amount to /dev/log/\* will result in a
 * ARC MOD END
 * truncated log entry.
 */
#define LOGGER_ENTRY_MAX_PAYLOAD	4076

/*
 * The maximum size of a log entry which can be read from the
 * kernel logger driver. An attempt to read less than this amount
 * may result in read() returning EINVAL.
 */
#define LOGGER_ENTRY_MAX_LEN		(5*1024)

#ifdef HAVE_IOCTL

#include <sys/ioctl.h>

#define __LOGGERIO	0xAE

#define LOGGER_GET_LOG_BUF_SIZE		_IO(__LOGGERIO, 1) /* size of log */
#define LOGGER_GET_LOG_LEN		_IO(__LOGGERIO, 2) /* used log len */
#define LOGGER_GET_NEXT_ENTRY_LEN	_IO(__LOGGERIO, 3) /* next entry len */
#define LOGGER_FLUSH_LOG		_IO(__LOGGERIO, 4) /* flush log */
#define LOGGER_GET_VERSION		_IO(__LOGGERIO, 5) /* abi version */
#define LOGGER_SET_VERSION		_IO(__LOGGERIO, 6) /* abi version */

#endif // HAVE_IOCTL

/* ARC MOD BEGIN */
#include <sys/types.h>
#include "common/alog.h"
#include "common/private/minimal_base.h"

template <typename T> struct DefaultSingletonTraits;

namespace arc {

class LoggerBuffer;
class LoggerReader;

class Logger {
 public:
  int Log(arc_log_id_t log_id, int prio, const char* tag, const char* msg);

  int LogEvent(int32_t tag, const void* payload, size_t len);

  int LogEventWithType(int32_t tag, char type, const void* payload,
      size_t len);

  // Create a new logger reader.
  LoggerReader* CreateReader(arc_log_id_t log_id);

  // Release a logger reader.
  void ReleaseReader(LoggerReader* reader);

  // Read a log entry from the given reader.
  ssize_t ReadLogEntry(LoggerReader* reader, struct logger_entry* entry,
      size_t len);

  // Return true if the reader is read ready.
  bool IsReadReady(LoggerReader* reader);

  // Wait for a read ready notification. The notification will be delivered by
  // the given callback.
  void WaitForReadReady(LoggerReader* reader, void (*callback)());

  // Get logger buffer size.
  size_t GetBufferSize(LoggerReader* reader);

  // Get size of readable logs.
  size_t GetLogLength(LoggerReader* reader);

  // Get next log entry length
  size_t GetNextEntryLength(LoggerReader* reader);

  // Clear logger buffer.
  void FlushBuffer(LoggerReader* reader);

  static Logger* GetInstance();

 private:
  friend struct DefaultSingletonTraits<Logger>;

  Logger();
  ~Logger();

  // TODO(crbug.com/391661): Use std::unique_ptr once we completely migrate to
  // clang.
  LoggerBuffer* buffers_[ARC_LOG_ID_MAX];

  COMMON_DISALLOW_COPY_AND_ASSIGN(Logger);
};

}  // namespace arc


#endif  // COMMON_LOGGER_H_
/* ARC MOD END */
