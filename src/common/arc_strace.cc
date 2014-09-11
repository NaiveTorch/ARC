// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/arc_strace.h"

#include <arpa/inet.h>
#include <ctype.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <nacl_stat.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>

#include <algorithm>
#include <map>
#include <numeric>
#include <stack>
#include <string>
#include <utility>

#include "base/basictypes.h"
#include "base/safe_strerror_posix.h"
#include "base/strings/string_util.h"
#include "base/strings/stringprintf.h"
#include "base/synchronization/lock.h"
#include "base/time/time.h"
#include "common/logd_write.h"
#include "common/options.h"
#include "common/process_emulator.h"
#include "ppapi/c/pp_errors.h"

#undef LOG_TAG
#define LOG_TAG "arc_strace"

#define STRACE_STATS_LOG(fmt, ...) \
  STRACE_LOG("%5d ! STATS " fmt, g_thread_id_manager->Get(), __VA_ARGS__)

#define STRACE_LOG(fmt, ...) \
  arc::WriteLog( \
      base::StringPrintf("[[arc_strace]]: " fmt "\n", __VA_ARGS__))

#define STRACE_WARN(fmt, ...) \
  arc::WriteLog(base::StringPrintf( \
      "[[arc_strace]]: [WARN] " fmt "\n", __VA_ARGS__))

namespace arc {

#if ENABLE_ARC_STRACE

// Whether to remove lines that could be considered noise.
static const bool kNoiseReductionMode = false;

bool g_arc_strace_enabled;

namespace {

typedef int ThreadID;

class ThreadIDManager* g_thread_id_manager;
class ArcStrace* g_arc_strace;
const char* g_plugin_type_prefix;

// A helper class which returns an appropriate unique ID for current
// thread. pthread_self() can be used for this purpose but it isn't
// very readable if pthread_t is a pointer type, so we'll generate a
// sequential ID for such platforms.
class ThreadIDManager {
 public:
  ThreadIDManager() {}

  ThreadID Get() {
    return gettid();
  }

 private:
  DISALLOW_COPY_AND_ASSIGN(ThreadIDManager);
};

// A class for implementing all the macros in the header. This class
// keeps track of various thread status such like the current function
// each thread is in.
class ArcStrace {
 public:
  ArcStrace() {
    BuildIgnoredCallPrefixes();
  }

  void Enter(const char* name, const char* format, va_list ap) {
    ThreadID tid = g_thread_id_manager->Get();

    std::string call = name;
    call += '(';
    base::StringAppendV(&call, format, ap);
    call += ')';

    const bool should_print = ShouldPrintCall(name, "", call);

    CallStackType* call_stack = GetCallStackForThreadID(tid);
    if (should_print) {
      STRACE_LOG("%s%5d %*s-> %s UID=%lld",
                 g_plugin_type_prefix,
                 tid, call_stack->size(), "", call.c_str(),
                 static_cast<int64_t>(ProcessEmulator::GetUid()));
    }
    const CallStackFrame new_frame =
        { kDefaultHandler, name, call, base::Time::Now(), should_print };
    call_stack->push(new_frame);
  }

  void EnterFD(const char* name, const char* format, va_list ap) {
    ThreadID tid = g_thread_id_manager->Get();

    // Consume %d and file descriptor in the first variable argument.
    // It's not possible to make file descriptor a non-variable
    // argument. There are some functions which don't have arguments
    // except file descriptor (e.g., close). The compiler will
    // complain for such functions because there are no variable
    // arguments for __attribute__((format(printf))) function.
    ALOG_ASSERT(format[0] == '%' && format[1] == 'd');
    format += 2;
    int fd = va_arg(ap, int);

    std::string call = name;
    call += base::StringPrintf("(%d ", fd);

    bool should_print = true;

    {
      base::AutoLock lock(mu_);
      FDToNameMap::const_iterator found = fd_to_name_.find(fd);
      if (found == fd_to_name_.end()) {
        call += "???";
        // -1 is a valid FD for mmap with MAP_ANONYMOUS.
        if (fd != -1)
          STRACE_WARN("%sUnknown FD! fd=%d", g_plugin_type_prefix, fd);
      } else {
        const char* path = found->second.c_str();
        should_print = ShouldPrintCall(name, path, call);
        call += base::StringPrintf("\"%s\"", path);
      }
    }

    if (*format)
      base::StringAppendV(&call, format, ap);
    call += ')';

    CallStackType* call_stack = GetCallStackForThreadID(tid);
    if (should_print) {
      STRACE_LOG("%s%5d %*s-> %s UID=%lld",
                 g_plugin_type_prefix,
                 tid, call_stack->size(), "", call.c_str(),
                 static_cast<int64_t>(ProcessEmulator::GetUid()));
    }
    const CallStackFrame new_frame =
        { kDefaultHandler, name, call, base::Time::Now(), should_print };
    call_stack->push(new_frame);
  }

  void ReportHandler(const char* handler_name) {
    ALOG_ASSERT(handler_name);
    ThreadID tid = g_thread_id_manager->Get();
    CallStackType* call_stack = GetCallStackForThreadID(tid);
    ALOG_ASSERT(!call_stack->empty());
    // Always overwrite the current one with |handler_name|.
    call_stack->top().handler = handler_name;
    ARC_STRACE_REPORT("handler=%s", handler_name);
  }

  void Report(const char* format, va_list ap) {
    ThreadID tid = g_thread_id_manager->Get();

    std::string msg;
    base::StringAppendV(&msg, format, ap);

    CallStackType* call_stack = GetCallStackForThreadID(tid);
    if (!call_stack->empty()) {
      const CallStackFrame& frame = call_stack->top();
      if (frame.should_print) {
        STRACE_LOG("%s%5d %*s | %s: %s",
                   g_plugin_type_prefix,
                   tid, call_stack->size() - 1, "",
                   frame.call.c_str(), msg.c_str());
      }
    } else {
      // ARC_STRACE_REPORT is called without ARC_STRACE_ENTER/RETURN.
      STRACE_LOG("%s%5d ! %s",
                 g_plugin_type_prefix, tid, msg.c_str());
    }
  }

  void Return(const std::string& retval, bool needs_strerror) {
    const base::Time now(base::Time::Now());
    ThreadID tid = g_thread_id_manager->Get();

    CallStackType* call_stack = GetCallStackForThreadID(tid);
    ALOG_ASSERT(!call_stack->empty(),
                "tid=%d retval=%s", tid, retval.c_str());

    std::string err;
    if (errno != 0 && needs_strerror)
      err = " (" + safe_strerror(errno) + ")";

    const CallStackFrame& frame = call_stack->top();
    const base::TimeDelta zero;
    base::TimeDelta delta = now - frame.start;
    if (delta < zero)
      delta = zero;
    const int64_t delta_msec = delta.InMilliseconds();
    if (frame.should_print) {
      STRACE_LOG("%s%5d %*s<- %s = %s%s <%lld.%03lld>",
                 g_plugin_type_prefix, tid, call_stack->size() - 1, "",
                 frame.call.c_str(),
                 retval.c_str(), err.c_str(), delta_msec / 1000,
                 delta_msec % 1000);
    }

    if (call_stack->size() == 1) {
      // Update |stats_| only when returning from the top-level function.
      // For example, __wrap_opendir internally calls __wrap_open, but we
      // do not update |stats_| when returning from __wrap_open. Similarly,
      // __wrap_dlopen might call constructors of a DSO, and the constructors
      // might call __wrap_* functions if the DSO is linked with -Wl,--wrap,
      // but here we ignore such wrap calls.
      const CallStatsType::key_type key =
          std::make_pair(frame.handler, frame.function);
      base::AutoLock lock(mu_);
      stats_[key].push_back(delta.InMicroseconds());
    }

    call_stack->pop();
  }

  void RegisterFD(int fd, const char* name) {
    base::AutoLock lock(mu_);
    RegisterFDLocked(fd, name);
  }

  void UnregisterFD(int fd) {
    base::AutoLock lock(mu_);
    if (!fd_to_name_.erase(fd)) {
      STRACE_WARN("%sUnregister unknown FD! fd=%d", g_plugin_type_prefix, fd);
    }
  }

  void DupFD(int oldfd, int newfd) {
    base::AutoLock lock(mu_);
    FDToNameMap::const_iterator found = fd_to_name_.find(oldfd);
    if (found == fd_to_name_.end()) {
      STRACE_WARN("%sDup unknown FD! oldfd=%d newfd=%d",
                  g_plugin_type_prefix, oldfd, newfd);
    } else {
      RegisterFDLocked(newfd, found->second.c_str());
    }
  }

  void DumpStats(const std::string& user_str) {
    STRACE_STATS_LOG("%s", "--------------------");
    STRACE_STATS_LOG("@ %s", user_str.c_str());  // e.g. "@ OnResume ..."

    // A map from a handler name to (occurrences, duration).
    typedef std::map<std::string,
                     std::pair<size_t, uint64_t> > PerHandlerDuration;
    PerHandlerDuration per_handler;

    {
      base::AutoLock lock(mu_);

      STRACE_STATS_LOG("%s", "Per-function results:");
      for (CallStatsType::iterator it = stats_.begin();
           it != stats_.end(); ++it) {
        const std::string& handler = it->first.first;
        const std::string& function = it->first.second;
        const size_t size = it->second.size();
        const uint64_t sum =
            std::accumulate(it->second.begin(), it->second.end(), 0);
        STRACE_STATS_LOG(
            "  %s %s: Occurrences: %zu, "
            "Duration: %lld us total (%lld us average), "
            "min/median/max: %lld/%lld/%lld us",
            handler.c_str(), function.c_str(), size,
            sum, sum / size,
            *std::min_element(it->second.begin(), it->second.end()),
            GetMedian(&it->second),
            *std::max_element(it->second.begin(), it->second.end()));
        per_handler[handler].first += size;
        per_handler[handler].second += sum;
      }
    }

    STRACE_STATS_LOG("%s", "Per-handler results:");
    for (PerHandlerDuration::const_iterator it = per_handler.begin();
         it != per_handler.end(); ++it) {
      STRACE_STATS_LOG("  %s *: Occurrences: %zu, "
                       "Duration: %lld us total (%lld us average)",
                       it->first.c_str(), it->second.first,
                       it->second.second, it->second.second / it->second.first);
    }
    STRACE_STATS_LOG("%s", "--------------------");
  }

  void ResetStats() {
    base::AutoLock lock(mu_);
    stats_.clear();
  }

 private:
  static const char kDefaultHandler[];
  struct CallStackFrame {
    std::string handler;
    std::string function;  // e.g. 'write'
    std::string call;  // e.g. 'write(5 "/foo/bar.txt", 0x..., 128)'
    base::Time start;
    bool should_print;
  };
  typedef std::stack<CallStackFrame> CallStackType;
  typedef std::map<int, std::string> FDToNameMap;
  // A map from (handler, func) to an array of elapsed time in us.
  typedef std::map<std::pair<std::string, std::string>,
                   std::vector<int64_t> > CallStatsType;

  void RegisterFDLocked(int fd, const char* name) {
    std::pair<FDToNameMap::iterator, bool> p =
        fd_to_name_.insert(std::make_pair(fd, name));
    if (!p.second) {
      STRACE_WARN("%sRegister the same FD twice! fd=%d orig=%s name=%s",
                  g_plugin_type_prefix, fd, p.first->second.c_str(), name);
      p.first->second = name;
    }
  }

  CallStackType* GetCallStackForThreadID(ThreadID tid) {
    base::AutoLock lock(mu_);
    return &tid_to_call_stack_[tid];
  }

  bool ShouldPrintCall(const std::string& name,
                       const std::string& file_path,
                       const std::string& call_str) {
    if (!kNoiseReductionMode)
      return true;

    if (name == "getpid" || name == "getuid")
      return false;

    if (file_path == "/sys/kernel/debug/tracing/trace_marker" ||
        file_path == "/system/usr/share/zoneinfo/tzdata" ||
        file_path == "/dev/urandom" ||
        file_path == "pipe[0]" ||
        file_path == "pipe[1]" ||
        file_path == "socketpair[0]" ||
        file_path == "socketpair[1]") {
      return false;
    }

    if (name == "epoll_wait" && file_path == "epoll")
      return false;

    for (size_t i = 0; i < ignored_file_path_prefixes_.size(); i++) {
      if (StartsWithASCII(file_path, ignored_file_path_prefixes_[i], true))
        return false;
    }

    for (size_t i = 0; i < ignored_call_prefixes_.size(); i++) {
      if (StartsWithASCII(call_str, ignored_call_prefixes_[i], true))
        return false;
    }

    return true;
  }

  void BuildIgnoredCallPrefixes() {
    if (!kNoiseReductionMode)
      return;

    static const std::string kIgnoredFilePrefixes[] = {
        "/data/misc/keychain/cacerts-removed/",
        "/system/etc/security/cacerts/",
        "/system/fonts/",
    };

    int prefix_count =
        sizeof(kIgnoredFilePrefixes) / sizeof(kIgnoredFilePrefixes[0]);
    for (int i = 0; i < prefix_count; i++) {
      const std::string& prefix = kIgnoredFilePrefixes[i];
      ignored_file_path_prefixes_.push_back(prefix);
      ignored_call_prefixes_.push_back(std::string("access(\"") + prefix);
      ignored_call_prefixes_.push_back(std::string("open(\"") + prefix);
      ignored_call_prefixes_.push_back(std::string("fopen(\"") + prefix);
      ignored_call_prefixes_.push_back(std::string("xstat(3, \"") + prefix);
    }
  }

  // Per-thread call stack.
  std::map<ThreadID, CallStackType> tid_to_call_stack_;
  FDToNameMap fd_to_name_;
  CallStatsType stats_;
  std::vector<std::string> ignored_file_path_prefixes_;
  std::vector<std::string> ignored_call_prefixes_;

  // Protects data members.
  base::Lock mu_;

  DISALLOW_COPY_AND_ASSIGN(ArcStrace);
};

const char ArcStrace::kDefaultHandler[] = "wrap";

void AppendResult(const std::string& addend, std::string* result) {
  if (addend.empty())
    return;
  if (!result->empty())
    *result += '|';
  *result += addend;
}

template <class Int>
inline bool AppendEnumStr(
    Int* val, int64_t enum_value, const char* enum_sym, std::string* result) {
  int64_t masked = *val & enum_value;
  // We need to check both 1) masked != 0 and 2) masked == enum_value.
  // Here is the reason:
  //
  // 1) RTLD_NOW is zero on Bionic, and we should not stringify such
  //    values.
  // 2) There are a few enum variables which have multiple bits. For
  //    example, O_SYNC is O_DSYNC|04000000. So, if we do not check
  //    |masked| equals to |enum_value|, O_DSYNC will be shown as
  //    O_SYNC.
  if (masked && masked == enum_value) {
    AppendResult(enum_sym, result);
    *val &= ~enum_value;
    return true;
  }
  return false;
}

}  // namespace

// Returns the median of |samples|. This function may reorder elements in
// the vector.
int64_t GetMedian(std::vector<int64_t>* samples) {
  ALOG_ASSERT(samples && !samples->empty());
  const size_t mid_index = samples->size() / 2;
  // Select |mid_index|-th smallest element in the vector and move it to
  // |samples->begin() + mid_index|. Then move all elements that are less
  // than or equal to the selected element to
  // [samples->begin(), samples->begin() + mid_index) in no particular order.
  std::nth_element(
      samples->begin(), samples->begin() + mid_index, samples->end());
  const int64_t mid_value = (*samples)[mid_index];
  // If the number of |samples| is odd, return the |mid_value|. If it is even,
  // compute and return the average of the two values in the middle.
  if (samples->size() % 2)
    return mid_value;
  return (mid_value + *std::max_element(
      samples->begin(), samples->begin() + mid_index - 1)) / 2;
}

void StraceEnter(const char* name, const char* format, ...) {
  ALOG_ASSERT(g_arc_strace);

  va_list ap;
  va_start(ap, format);
  g_arc_strace->Enter(name, format, ap);
  va_end(ap);
}

void StraceEnterFD(const char* name, const char* format, ...) {
  ALOG_ASSERT(g_arc_strace);

  va_list ap;
  va_start(ap, format);
  g_arc_strace->EnterFD(name, format, ap);
  va_end(ap);
}

void StraceReportHandler(const char* handler_name) {
  ALOG_ASSERT(g_arc_strace);
  g_arc_strace->ReportHandler(handler_name);
}

void StraceReport(const char* format, ...) {
  ALOG_ASSERT(g_arc_strace);

  va_list ap;
  va_start(ap, format);
  g_arc_strace->Report(format, ap);
  va_end(ap);
}

void StraceReturn(ssize_t retval) {
  const bool needs_strerror = (retval < 0);
  StraceReturnInt(retval, needs_strerror);
}

void StraceReturnPtr(void* retval, bool needs_strerror) {
  ALOG_ASSERT(g_arc_strace);

  g_arc_strace->Return(base::StringPrintf("%p", retval), needs_strerror);
}

void StraceReturnInt(ssize_t retval, bool needs_strerror) {
  ALOG_ASSERT(g_arc_strace);

  g_arc_strace->Return(
      base::StringPrintf("%lld", static_cast<int64_t>(retval)), needs_strerror);
}

void StraceRegisterFD(int fd, const char* name) {
  ALOG_ASSERT(g_arc_strace);

  if (fd >= 0)
    g_arc_strace->RegisterFD(fd, name ? name : "(null)");
}

void StraceUnregisterFD(int fd) {
  ALOG_ASSERT(g_arc_strace);

  g_arc_strace->UnregisterFD(fd);
}

void StraceDupFD(int oldfd, int newfd) {
  ALOG_ASSERT(g_arc_strace);

  if (newfd >= 0)
    g_arc_strace->DupFD(oldfd, newfd);
}

void StraceDumpStats(const std::string& user_str) {
  ALOG_ASSERT(g_arc_strace);
  g_arc_strace->DumpStats(user_str);
}

void StraceResetStats() {
  ALOG_ASSERT(g_arc_strace);
  g_arc_strace->ResetStats();
}

void StraceInit(const std::string& plugin_type_prefix) {
  ALOG_ASSERT(!g_arc_strace);
  if (Options::GetInstance()->enable_arc_strace) {
    g_arc_strace_enabled = true;
    // Note these global variables will be never freed.
    g_arc_strace = new ArcStrace();
    g_thread_id_manager = new ThreadIDManager();
    g_plugin_type_prefix = strdup(plugin_type_prefix.c_str());
  }
}

#define APPEND_ENUM_STR(val, enum_sym, result)  \
  AppendEnumStr(&val, enum_sym, #enum_sym, &result)

#define CASE_APPEND_ENUM_STR(enum_sym, result)  \
  case enum_sym: AppendResult(#enum_sym, &result); break

std::string GetAccessModeStr(int mode) {
  std::string result;
  APPEND_ENUM_STR(mode, R_OK, result);
  APPEND_ENUM_STR(mode, W_OK, result);
  APPEND_ENUM_STR(mode, X_OK, result);
  if (mode)
    AppendResult(base::StringPrintf("%d???", mode), &result);
  if (result.empty())
    result = "F_OK";
  return result;
}

std::string GetOpenFlagStr(int flag) {
  std::string result;
  int accmode = flag & O_ACCMODE;
  if (accmode == O_RDONLY)
    result += "O_RDONLY";
  else if (accmode == O_WRONLY)
    result += "O_WRONLY";
  else if (accmode == O_RDWR)
    result += "O_RDWR";
  else
    result += base::StringPrintf("BAD_O_ACCMODE(%d)", accmode);
  flag &= ~O_ACCMODE;
  APPEND_ENUM_STR(flag, O_CREAT, result);
  APPEND_ENUM_STR(flag, O_EXCL, result);
  APPEND_ENUM_STR(flag, O_NOCTTY, result);
  APPEND_ENUM_STR(flag, O_TRUNC, result);
  APPEND_ENUM_STR(flag, O_APPEND, result);
  APPEND_ENUM_STR(flag, O_NONBLOCK, result);
  APPEND_ENUM_STR(flag, O_SYNC, result);
  APPEND_ENUM_STR(flag, O_ASYNC, result);
  APPEND_ENUM_STR(flag, O_DSYNC, result);
  APPEND_ENUM_STR(flag, O_DIRECTORY, result);
  APPEND_ENUM_STR(flag, O_NOFOLLOW, result);
  APPEND_ENUM_STR(flag, O_CLOEXEC, result);
  APPEND_ENUM_STR(flag, O_DIRECT, result);
  APPEND_ENUM_STR(flag, O_NOATIME, result);
  APPEND_ENUM_STR(flag, O_LARGEFILE, result);
  APPEND_ENUM_STR(flag, O_PATH, result);
  if (flag)
    AppendResult(base::StringPrintf("%d???", flag), &result);
  if (result.empty())
    result = "0";
  return result;
}

std::string GetDlopenFlagStr(int flag) {
  std::string result;
  APPEND_ENUM_STR(flag, RTLD_LAZY, result);
  APPEND_ENUM_STR(flag, RTLD_NOW, result);
  if (!APPEND_ENUM_STR(flag, RTLD_GLOBAL, result))
    AppendResult("RTLD_LOCAL", &result);
  if (flag)
    AppendResult(base::StringPrintf("%d???", flag), &result);
  return result;
}

std::string GetMmapProtStr(int prot) {
  std::string result;
  APPEND_ENUM_STR(prot, PROT_READ, result);
  APPEND_ENUM_STR(prot, PROT_WRITE, result);
  APPEND_ENUM_STR(prot, PROT_EXEC, result);
  APPEND_ENUM_STR(prot, PROT_GROWSDOWN, result);
  APPEND_ENUM_STR(prot, PROT_GROWSUP, result);
  if (prot)
    AppendResult(base::StringPrintf("%d???", prot), &result);
  if (result.empty())
    result = "PROT_NONE";
  return result;
}

std::string GetMmapFlagStr(int flag) {
  std::string result;
  APPEND_ENUM_STR(flag, MAP_SHARED, result);
  APPEND_ENUM_STR(flag, MAP_PRIVATE, result);
  APPEND_ENUM_STR(flag, MAP_FIXED, result);
  if (!APPEND_ENUM_STR(flag, MAP_ANONYMOUS, result))
    AppendResult("MAP_FILE", &result);
#if defined(__native_client__) || defined(__linux__)
  APPEND_ENUM_STR(flag, MAP_GROWSDOWN, result);
  APPEND_ENUM_STR(flag, MAP_DENYWRITE, result);
  APPEND_ENUM_STR(flag, MAP_EXECUTABLE, result);
  APPEND_ENUM_STR(flag, MAP_LOCKED, result);
  APPEND_ENUM_STR(flag, MAP_NORESERVE, result);
  APPEND_ENUM_STR(flag, MAP_POPULATE, result);
  APPEND_ENUM_STR(flag, MAP_NONBLOCK, result);
#if !defined(__arm__)
  APPEND_ENUM_STR(flag, MAP_STACK, result);
#endif
#endif
#if !defined(__native_client__) && defined(__linux__) && !defined(__arm__)
  APPEND_ENUM_STR(flag, MAP_HUGETLB, result);
#endif
  if (flag)
    AppendResult(base::StringPrintf("%d???", flag), &result);
  return result;
}

std::string GetSocketDomainStr(int domain) {
  std::string result;
  switch (domain) {
    CASE_APPEND_ENUM_STR(AF_UNIX, result);
    CASE_APPEND_ENUM_STR(AF_INET, result);
    CASE_APPEND_ENUM_STR(AF_INET6, result);
    CASE_APPEND_ENUM_STR(AF_IPX, result);
    CASE_APPEND_ENUM_STR(AF_NETLINK, result);
    CASE_APPEND_ENUM_STR(AF_X25, result);
    CASE_APPEND_ENUM_STR(AF_AX25, result);
    CASE_APPEND_ENUM_STR(AF_ATMPVC, result);
    CASE_APPEND_ENUM_STR(AF_APPLETALK, result);
    CASE_APPEND_ENUM_STR(AF_PACKET, result);
    default: AppendResult(base::StringPrintf("%d???", domain), &result);
  }
  return result;
}

std::string GetSocketTypeStr(int type) {
  // Parse options first to drop their bits from |type|.
  std::string opts;
  std::string result;
  switch (type) {
    CASE_APPEND_ENUM_STR(SOCK_STREAM, result);
    CASE_APPEND_ENUM_STR(SOCK_DGRAM, result);
    CASE_APPEND_ENUM_STR(SOCK_SEQPACKET, result);
    CASE_APPEND_ENUM_STR(SOCK_RAW, result);
    CASE_APPEND_ENUM_STR(SOCK_RDM, result);
    CASE_APPEND_ENUM_STR(SOCK_PACKET, result);
    default: AppendResult(base::StringPrintf("%d???", type), &result);
  }

  AppendResult(opts, &result);
  return result;
}

std::string GetSocketProtocolStr(int protocol) {
  std::string result;
  switch (protocol) {
    CASE_APPEND_ENUM_STR(IPPROTO_IP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_ICMP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_IGMP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_IPIP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_TCP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_EGP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_PUP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_UDP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_IDP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_DCCP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_IPV6, result);
    CASE_APPEND_ENUM_STR(IPPROTO_ROUTING, result);
    CASE_APPEND_ENUM_STR(IPPROTO_FRAGMENT, result);
    CASE_APPEND_ENUM_STR(IPPROTO_RSVP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_GRE, result);
    CASE_APPEND_ENUM_STR(IPPROTO_ESP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_AH, result);
    CASE_APPEND_ENUM_STR(IPPROTO_ICMPV6, result);
    CASE_APPEND_ENUM_STR(IPPROTO_NONE, result);
    CASE_APPEND_ENUM_STR(IPPROTO_DSTOPTS, result);
    CASE_APPEND_ENUM_STR(IPPROTO_PIM, result);
    CASE_APPEND_ENUM_STR(IPPROTO_COMP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_SCTP, result);
    CASE_APPEND_ENUM_STR(IPPROTO_RAW, result);
    default: AppendResult(base::StringPrintf("%d???", protocol), &result);
  }
  return result;
}

std::string GetFlockOperationStr(int operation) {
  std::string result;
  switch (operation & ~LOCK_NB) {
    CASE_APPEND_ENUM_STR(LOCK_SH, result);
    CASE_APPEND_ENUM_STR(LOCK_EX, result);
    CASE_APPEND_ENUM_STR(LOCK_UN, result);
    default: AppendResult(base::StringPrintf("%d???", operation), &result);
  }
  APPEND_ENUM_STR(operation, LOCK_NB, result);
  return result;
}

std::string GetLseekWhenceStr(int whence) {
  std::string result;
  switch (whence) {
    CASE_APPEND_ENUM_STR(SEEK_SET, result);
    CASE_APPEND_ENUM_STR(SEEK_CUR, result);
    CASE_APPEND_ENUM_STR(SEEK_END, result);
    default: AppendResult(base::StringPrintf("%d???", whence), &result);
  }
  return result;
}

std::string GetMremapFlagStr(int flag) {
  std::string result;
  APPEND_ENUM_STR(flag, MREMAP_MAYMOVE, result);
  APPEND_ENUM_STR(flag, MREMAP_FIXED, result);
  if (flag)
    AppendResult(base::StringPrintf("%d???", flag), &result);
  if (result.empty())
    result = "0";
  return result;
}

std::string GetSockaddrStr(const struct sockaddr* addr) {
  if (!addr)
    return "(null)";

  std::string result = "{family=" + GetSocketDomainStr(addr->sa_family);
  switch (addr->sa_family) {
    case AF_INET: {
      const struct sockaddr_in* in =
          reinterpret_cast<const struct sockaddr_in*>(addr);
      std::string v4_addr;
      uint32_t addr_val = ntohl(in->sin_addr.s_addr);
      for (int i = 3; i >=0; --i) {
        if (!v4_addr.empty())
          v4_addr += '.';
        v4_addr += base::StringPrintf("%u", (addr_val >> (i * 8)) & 255);
      }
      result += base::StringPrintf(" port=%hu addr=%s",
                                   ntohs(in->sin_port), v4_addr.c_str());
      break;
    }
    case AF_INET6: {
      const struct sockaddr_in6* in6 =
          reinterpret_cast<const struct sockaddr_in6*>(addr);
      std::string v6_addr;
      for (int i = 0; i < 8; i++) {
        if (!v6_addr.empty())
          v6_addr += ':';
        v6_addr +=
            base::StringPrintf("%04hx", ntohs(in6->sin6_addr.s6_addr16[i]));
      }
      result += base::StringPrintf(" port=%hu flowinfo=%u addr=%s scope_id=%u",
                                   ntohs(in6->sin6_port), in6->sin6_flowinfo,
                                   v6_addr.c_str(), in6->sin6_scope_id);
      break;
    }
    case AF_UNIX: {
      const struct sockaddr_un* un =
          reinterpret_cast<const struct sockaddr_un*>(addr);
      result += base::StringPrintf(" path=%s", un->sun_path);
      break;
    }
    default:
      result += " ...";
  }
  result += "}";
  return result;
}

std::string GetDirentStr(const struct dirent* ent) {
  std::string type;
  switch (ent->d_type) {
    CASE_APPEND_ENUM_STR(DT_BLK, type);
    CASE_APPEND_ENUM_STR(DT_CHR, type);
    CASE_APPEND_ENUM_STR(DT_DIR, type);
    CASE_APPEND_ENUM_STR(DT_FIFO, type);
    CASE_APPEND_ENUM_STR(DT_LNK, type);
    CASE_APPEND_ENUM_STR(DT_REG, type);
    CASE_APPEND_ENUM_STR(DT_SOCK, type);
    CASE_APPEND_ENUM_STR(DT_UNKNOWN, type);
    default:
      type = "???";
  }
  return base::StringPrintf(
      "{name=\"%s\" type=%s off=%lld ino=%lld reclen=%hu}",
      ent->d_name,
      type.c_str(),
      static_cast<int64_t>(ent->d_off),
      static_cast<int64_t>(ent->d_ino),
      ent->d_reclen);
}

static std::string GetStatModeStr(mode_t mode) {
  std::string result;
  switch (mode & S_IFMT) {
    CASE_APPEND_ENUM_STR(S_IFSOCK, result);
    CASE_APPEND_ENUM_STR(S_IFLNK, result);
    CASE_APPEND_ENUM_STR(S_IFREG, result);
    CASE_APPEND_ENUM_STR(S_IFBLK, result);
    CASE_APPEND_ENUM_STR(S_IFDIR, result);
    CASE_APPEND_ENUM_STR(S_IFCHR, result);
    CASE_APPEND_ENUM_STR(S_IFIFO, result);
    default:
      result = "???";
  }
  if ((mode & S_ISUID))
    AppendResult("S_ISUID", &result);
  if ((mode & S_ISGID))
    AppendResult("S_ISGID", &result);
  if ((mode & S_ISVTX))
    AppendResult("S_ISVTX", &result);
  AppendResult(base::StringPrintf("0%o", mode & 0777), &result);
  return result;
}

std::string GetStatStr(const struct stat* st) {
  return base::StringPrintf(
      "{dev=%lld ino=%lld mode=%s nlink=%lld uid=%lld gid=%lld rdev=%lld"
      " size=%lld blksize=%lld blkcnt=%lld atime=%lld mtime=%lld ctime=%lld}",
      static_cast<int64_t>(st->st_dev),
      static_cast<int64_t>(st->st_ino),
      GetStatModeStr(st->st_mode).c_str(),
      static_cast<int64_t>(st->st_nlink),
      static_cast<int64_t>(st->st_uid),
      static_cast<int64_t>(st->st_gid),
      static_cast<int64_t>(st->st_rdev),
      static_cast<int64_t>(st->st_size),
      static_cast<int64_t>(st->st_blksize),
      static_cast<int64_t>(st->st_blocks),
      static_cast<int64_t>(st->st_atime),
      static_cast<int64_t>(st->st_mtime),
      static_cast<int64_t>(st->st_ctime));
}

std::string GetNaClAbiStatStr(const struct nacl_abi_stat* st) {
  return base::StringPrintf(
      "{dev=%lld ino=%lld mode=%s nlink=%lld uid=%lld gid=%lld rdev=%lld"
      " size=%lld blksize=%lld blkcnt=%lld atime=%lld mtime=%lld ctime=%lld}",
      static_cast<int64_t>(st->nacl_abi_st_dev),
      static_cast<int64_t>(st->nacl_abi_st_ino),
      GetStatModeStr(st->nacl_abi_st_mode).c_str(),
      static_cast<int64_t>(st->nacl_abi_st_nlink),
      static_cast<int64_t>(st->nacl_abi_st_uid),
      static_cast<int64_t>(st->nacl_abi_st_gid),
      static_cast<int64_t>(st->nacl_abi_st_rdev),
      static_cast<int64_t>(st->nacl_abi_st_size),
      static_cast<int64_t>(st->nacl_abi_st_blksize),
      static_cast<int64_t>(st->nacl_abi_st_blocks),
      static_cast<int64_t>(st->nacl_abi_st_atime),
      static_cast<int64_t>(st->nacl_abi_st_mtime),
      static_cast<int64_t>(st->nacl_abi_st_ctime));
}

std::string GetFcntlCommandStr(int cmd) {
  std::string result;
  switch (cmd) {
    CASE_APPEND_ENUM_STR(F_DUPFD, result);
    CASE_APPEND_ENUM_STR(F_GETFD, result);
    CASE_APPEND_ENUM_STR(F_GETFL, result);
    CASE_APPEND_ENUM_STR(F_GETLEASE, result);
    CASE_APPEND_ENUM_STR(F_GETLK, result);
    CASE_APPEND_ENUM_STR(F_GETOWN, result);
    CASE_APPEND_ENUM_STR(F_GETSIG, result);
    CASE_APPEND_ENUM_STR(F_NOTIFY, result);
    CASE_APPEND_ENUM_STR(F_SETFD, result);
    CASE_APPEND_ENUM_STR(F_SETFL, result);
    CASE_APPEND_ENUM_STR(F_SETLEASE, result);
    CASE_APPEND_ENUM_STR(F_SETLK, result);
    CASE_APPEND_ENUM_STR(F_SETLKW, result);
    CASE_APPEND_ENUM_STR(F_SETOWN, result);
    CASE_APPEND_ENUM_STR(F_SETSIG, result);
    CASE_APPEND_ENUM_STR(F_GETLK64, result);
    CASE_APPEND_ENUM_STR(F_SETLK64, result);
    CASE_APPEND_ENUM_STR(F_SETLKW64, result);
    default: AppendResult(base::StringPrintf("%d???", cmd), &result);
  }
  return result;
}

std::string GetRWBufStr(const void* buf, size_t count) {
  static const size_t kStrSizeMax = 32;
  const char* str = static_cast<const char*>(buf);
  const size_t out_count = std::min(count, kStrSizeMax);
  std::string result("\"");
  for (size_t i = 0; i < out_count; i++) {
    const unsigned char c = str[i];
    if (c == '"')
      result += "\\\"";
    else if (c < 128 && isprint(c))
      result += c;
    else if (c == '\n')
      result += "\\n";
    else if (c == '\r')
      result += "\\r";
    else if (c == '\t')
      result += "\\t";
    else
      result += base::StringPrintf("\\%o", c);
  }
  result += '"';
  if (out_count != count)
    result += "...";
  return result;
}

std::string GetPPErrorStr(int32_t err) {
  std::string result;
  switch (err) {
    CASE_APPEND_ENUM_STR(PP_OK, result);
    CASE_APPEND_ENUM_STR(PP_OK_COMPLETIONPENDING, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_FAILED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_ABORTED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_BADARGUMENT, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_BADRESOURCE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOINTERFACE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOACCESS, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOMEMORY, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOSPACE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOQUOTA, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_INPROGRESS, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOTSUPPORTED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_BLOCKS_MAIN_THREAD, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_FILENOTFOUND, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_FILETOOBIG, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_FILECHANGED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NOTAFILE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_TIMEDOUT, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_USERCANCEL, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NO_USER_GESTURE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONTEXT_LOST, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NO_MESSAGE_LOOP, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_WRONG_THREAD, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_CLOSED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_RESET, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_REFUSED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_ABORTED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_FAILED, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_CONNECTION_TIMEDOUT, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_ADDRESS_INVALID, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_ADDRESS_UNREACHABLE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_ADDRESS_IN_USE, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_MESSAGE_TOO_BIG, result);
    CASE_APPEND_ENUM_STR(PP_ERROR_NAME_NOT_RESOLVED, result);
    default:
      result = "???";
  }
  return result;
}

std::string GetDlsymHandleStr(const void* handle) {
  if (handle == RTLD_DEFAULT)
    return "RTLD_DEFAULT";
  if (handle == RTLD_NEXT)
    return "RTLD_NEXT";
  return base::StringPrintf("%p", handle);
}

#else

void StraceInit(const std::string&) {}

#endif  // ENABLE_ARC_STRACE

}  // namespace arc
