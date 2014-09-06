// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// strace-like tracer for wrapped functions.
//
// A typical __wrap function looks like
//
// int __wrap_foobar(int arg1, int arg2) {
//   ARC_STRACE_ENTER("foobar", "%d, %d", arg1, arg2);
//   int result;
//   if (use_pepper) {
//     // You can call ARC_STRACE_REPORT to add information.
//     result = HandleFoobarWithPepper(arg1, arg2);
//   } else {
//     ARC_STRACE_REPORT("falling back to __real");
//     result = __real_foobar(arg1, arg2);
//   }
//   ARC_STRACE_RETURN(result);
// }
//
// If the __wrap function takes a file descriptor as an arguments, use
// ARC_STRACE_ENTER_FD instead of ARC_STRACE_ENTER.
//
// If the __wrap function opens/closes/dups a file descriptor, use
// ARC_STRACE_REGISTER_FD, ARC_STRACE_UNREGISTER_FD, and
// ARC_STRACE_DUP_FD, respectively.
//

#ifndef COMMON_ARC_STRACE_H_
#define COMMON_ARC_STRACE_H_

#include <dirent.h>
#include <stdint.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <string>
#include <vector>

#include "common/alog.h"

struct nacl_abi_stat;

namespace arc {

#define ENABLE_ARC_STRACE (!LOG_NDEBUG)

void StraceInit(const std::string& plugin_type_prefix);

// Make C string safe to be formatted by %s.
#define SAFE_CSTR(s) (s) ? (s) : "(null)"

#if ENABLE_ARC_STRACE

extern bool g_arc_strace_enabled;
inline bool StraceEnabled() {
  return g_arc_strace_enabled;
}

#define ATTR_PRINTF(x, y) __attribute__((format(printf, x, y)))

void StraceEnter(const char* name, const char* format, ...) ATTR_PRINTF(2, 3);
void StraceEnterFD(const char* name, const char* format, ...)
    ATTR_PRINTF(2, 3);
void StraceReportHandler(const char* handler_name);
void StraceReport(const char* format, ...) ATTR_PRINTF(1, 2);
void StraceReturn(ssize_t retval);
void StraceReturnPtr(void* retval, bool needs_strerror);
void StraceReturnInt(ssize_t retval, bool needs_strerror);
void StraceRegisterFD(int fd, const char* name);
void StraceUnregisterFD(int fd);
void StraceDupFD(int oldfd, int newfd);
void StraceDumpStats(const std::string& user_str);
void StraceResetStats();

// Pretty printers for enum values.
std::string GetAccessModeStr(int mode);
std::string GetOpenFlagStr(int flag);
std::string GetDlopenFlagStr(int flag);
std::string GetMmapProtStr(int prot);
std::string GetMmapFlagStr(int flag);
std::string GetSocketDomainStr(int domain);
std::string GetSocketTypeStr(int type);
std::string GetSocketProtocolStr(int protocol);
std::string GetFlockOperationStr(int operation);
std::string GetLseekWhenceStr(int whence);
std::string GetMremapFlagStr(int flag);
std::string GetFcntlCommandStr(int cmd);

// Pretty printers for struct values.
std::string GetSockaddrStr(const struct sockaddr* addr);
std::string GetDirentStr(const struct dirent* ent);
std::string GetStatStr(const struct stat* st);
std::string GetNaClAbiStatStr(const struct nacl_abi_stat* st);

// Pretty printers for other constants.
std::string GetDlsymHandleStr(const void* handle);

// A pretty printer for buffers passed to read/write.
std::string GetRWBufStr(const void* buf, size_t count);

// A pretty printer for third_party/chromium-ppapi/ppapi/c/pp_errors.h.
std::string GetPPErrorStr(int32_t err);

// For testing.
int64_t GetMedian(std::vector<int64_t>* samples);

// ARC_STRACE_ENTER(const char* name, const char* format, ...)
//
// |name| is the name of function and |format| is printf format to
// display variable arguments. You must call ARC_STRACE_RETURN* if
// you called this.
# define ARC_STRACE_ENTER(...) do {           \
    if (arc::StraceEnabled())                 \
      arc::StraceEnter(__VA_ARGS__);          \
  } while (0)

// ARC_STRACE_ENTER_FD(const char* name, const char* format, int fd, ...)
//
// The pathname or stream type of |fd| will be displayed. |format|
// must start with "%d". Otherwise, this is as same as ARC_STRACE_ENTER.
# define ARC_STRACE_ENTER_FD(...) do {        \
    if (arc::StraceEnabled())                 \
      arc::StraceEnterFD(__VA_ARGS__);        \
  } while (0)

// ARC_STRACE_REPORT_HANDLER(const char* handler_name)
//
// Adds information that |handler_name| (e.g. "MemoryFileSystem") handles
// the current task. The information is used in ARC_STRACE_DUMP_STATS.
# define ARC_STRACE_REPORT_HANDLER(handler_name) do {  \
    if (arc::StraceEnabled())                          \
      arc::StraceReportHandler(handler_name);          \
  } while (0)

// ARC_STRACE_REPORT(const char* format, ...)
//
// Adds information to the recently called function. You must call
// this function after you called ARC_STRACE_ENTER* and before you
// call ARC_STRACE_RETURN*.
# define ARC_STRACE_REPORT(...) do {          \
    if (arc::StraceEnabled())                 \
      arc::StraceReport(__VA_ARGS__);         \
  } while (0)

// ARC_STRACE_REPORT_PP_ERROR(err)
//
// Adds Pepper error information to the recently called function.
// See ARC_STRACE_REPORT for more detail.
# define ARC_STRACE_REPORT_PP_ERROR(err) do {                         \
    if (arc::StraceEnabled() && err)                                  \
    ARC_STRACE_REPORT("%s", arc::GetPPErrorStr(err).c_str());       \
  } while (0)

// ARC_STRACE_RETURN(ssize_t retval)
//
// Prints the information of the recently called function an returns
// retval. This assumes the wrapped function succeeded if retval >= 0.
// You must return from wrapped functions by this if you called
// ARC_STRACE_ENTER*. Note: |retval| might be evaluated twice.
# define ARC_STRACE_RETURN(retval) do {               \
    if (arc::StraceEnabled())                         \
      arc::StraceReturn(retval);                      \
    return retval;                                      \
  } while (0)

// ARC_STRACE_RETURN_PTR(void* retval, bool needs_strerror)
//
// A variant of ARC_STRACE_RETURN which returns a pointer value.
// Note: |retval| might be evaluated twice.
# define ARC_STRACE_RETURN_PTR(retval, needs_strerror) do {   \
    if (arc::StraceEnabled())                                 \
      arc::StraceReturnPtr(retval, needs_strerror);           \
    return retval;                                              \
  } while (0)

// ARC_STRACE_RETURN_INT(ssize_t retval, bool needs_strerror)
//
// A variant of ARC_STRACE_RETURN for a function which does not
// set |errno| on error. Note: |retval| might be evaluated twice.
# define ARC_STRACE_RETURN_INT(retval, needs_strerror) do {   \
    if (arc::StraceEnabled())                                 \
      arc::StraceReturnInt(retval, needs_strerror);           \
    return retval;                                              \
  } while (0)

// ARC_STRACE_RETURN_VOID()
//
// A variant of ARC_STRACE_RETURN which returns no value.
# define ARC_STRACE_RETURN_VOID() do {                \
    if (arc::StraceEnabled())                         \
      arc::StraceReturn(0);                           \
    return;                                             \
  } while (0)

// ARC_STRACE_REGISTER_FD(int fd, const char* name)
//
// Registers a new file descriptor. This |name| will be used to pretty
// print file descriptors passed by ARC_STRACE_ENTER_FD.
# define ARC_STRACE_REGISTER_FD(...) do {     \
    if (arc::StraceEnabled())                 \
      arc::StraceRegisterFD(__VA_ARGS__);     \
  } while (0)

// ARC_STRACE_UNREGISTER_FD(int fd)
//
// Unregisters |fd|.
# define ARC_STRACE_UNREGISTER_FD(...) do {   \
    if (arc::StraceEnabled())                 \
      arc::StraceUnregisterFD(__VA_ARGS__);   \
  } while (0)

// ARC_STRACE_DUP_FD(int oldfd, int newfd)
//
// Copies the name of |oldfd| to |newfd|.
# define ARC_STRACE_DUP_FD(...) do {          \
    if (arc::StraceEnabled())                 \
      arc::StraceDupFD(__VA_ARGS__);          \
  } while (0)

// ARC_STRACE_DUMP_STATS(const char* user_str)
//
// Dumps function call statistics to the log file. |user_str| is
// used as the header of the information.
# define ARC_STRACE_DUMP_STATS(user_str) do {  \
    if (arc::StraceEnabled())                  \
      arc::StraceDumpStats(user_str);          \
  } while (0)

// ARC_STRACE_RESET_STATS()
//
// Resets the statistics.
# define ARC_STRACE_RESET_STATS() do {         \
    if (arc::StraceEnabled())                  \
      arc::StraceResetStats();                 \
  } while (0)

#else  // ENABLE_ARC_STRACE

// TODO(crbug.com/345825): Reorganize the macros.
# define ARC_STRACE_ENTER(...)
# define ARC_STRACE_ENTER_FD(...)
# define ARC_STRACE_REPORT_HANDLER(handler_name)
# define ARC_STRACE_REPORT(...)
# define ARC_STRACE_REPORT_PP_ERROR(...)
# define ARC_STRACE_RETURN(retval) return retval
# define ARC_STRACE_RETURN_PTR(retval, needs_strerror) return retval
# define ARC_STRACE_RETURN_INT(retval, needs_strerror) return retval
# define ARC_STRACE_RETURN_VOID() return
# define ARC_STRACE_REGISTER_FD(...)
# define ARC_STRACE_UNREGISTER_FD(...)
# define ARC_STRACE_DUP_FD(...)
# define ARC_STRACE_DUMP_STATS(user_str)
# define ARC_STRACE_RESET_STATS()

#endif  // ENABLE_ARC_STRACE

}  // namespace arc

#endif  // COMMON_ARC_STRACE_H_
