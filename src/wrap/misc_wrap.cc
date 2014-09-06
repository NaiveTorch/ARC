/* Copyright 2014 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Simple wrapper for functions not related to file/socket such as
 * madvise.
 */

#include <errno.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#include <map>

#include "base/memory/singleton.h"
#include "base/synchronization/lock.h"
#include "common/arc_strace.h"
#include "common/backtrace.h"
#include "common/danger.h"

template <typename T> struct DefaultSingletonTraits;

extern "C" {
void __wrap_abort();
void __wrap_exit(int status);
int __wrap_fork();
int __wrap_getpriority(int which, int who);
int __wrap_getrlimit(int resource, struct rlimit *rlim);
int __wrap_kill(pid_t pid, int sig);
int __wrap_madvise(void* addr, size_t length, int advice);
int __wrap_pthread_kill(pthread_t thread, int sig);
int __wrap_setpriority(int which, int who, int prio);
int __wrap_setrlimit(int resource, const struct rlimit *rlim);
int __wrap_sigaction(int signum, const struct sigaction *act,
                     struct sigaction *oldact);
int __wrap_tgkill(int tgid, int tid, int sig);
int __wrap_tkill(int tid, int sig);
int __wrap_uname(struct utsname* buf);
int __wrap_vfork();
pid_t __wrap_wait(int *status);
pid_t __wrap_waitpid(pid_t pid, int *status, int options);
int __wrap_waitid(idtype_t idtype, id_t id, siginfo_t *infop, int options);
pid_t __wrap_wait3(int *status, int options, struct rusage *rusage);
pid_t __wrap_wait4(pid_t pid, int *status, int options, struct rusage *rusage);

extern void __real_abort();
extern void __real_exit(int status);
}  // extern "C"

namespace {

// Highest possible priority, see frameworks/native/include/utils/ThreadDefs.h.
const int ANDROID_PRIORITY_HIGHEST = -20;

// Initial value is set to a value that is usually not used. This will
// happen if atexit handler is called without __wrap_exit being
// called. For example, when user returns from main().
const int DEFAULT_EXIT_STATUS = 111;

// Store status code in __wrap_exit(), then read it from a function
// which is registered to atexit().
int g_exit_status = DEFAULT_EXIT_STATUS;

// get/setpriority is not currently supported. It is not yet clear how we
// should deal with thread priorities in ARC. Remember and return
// them for now.
class PriorityMap {
 public:
  static PriorityMap* GetInstance() {
    return Singleton<PriorityMap, LeakySingletonTraits<PriorityMap> >::get();
  }

  int GetPriority(int pid);
  void SetPriority(int pid, int priority);

 private:
  friend struct DefaultSingletonTraits<PriorityMap>;

  PriorityMap() {}
  ~PriorityMap() {}

  base::Lock mu_;
  // This actually maps 'tid' to priority, but because get/setpriority
  // specifies that we use process identifiers we name the map as pid-based.
  std::map<int, int> pid_to_priority_;

  DISALLOW_COPY_AND_ASSIGN(PriorityMap);
};

int PriorityMap::GetPriority(int pid) {
  base::AutoLock lock(mu_);
  return pid_to_priority_[pid];
}

void PriorityMap::SetPriority(int pid, int priority) {
  base::AutoLock lock(mu_);
  pid_to_priority_[pid] = priority;
}

}  // namespace

namespace arc {

int GetExitStatus() {
  return g_exit_status;
}

}  // namespace arc

//
// Function wrappers, sorted by function name.
//

/* Attempt to show the backtrace in abort(). */
void __wrap_abort() {
  arc::BacktraceInterface::Print();
  __real_abort();
}

// TODO(crbug.com/323815): __wrap_exit does not work against loader exit(),
// and _exit().
void __wrap_exit(int status) {
  ARC_STRACE_ENTER("exit", "%d", status);
  // We do not use mutex lock here since stored |g_exit_status| is read from
  // the same thread inside __real_exit() through atexit() functions chain.
  g_exit_status = status;
  __real_exit(status);
}

/* fork/vfork is currently not supported in NaCl mode. It also causes several
 * other issues in trusted mode (crbug.com/268645).
 */
int __wrap_fork() {
  ARC_STRACE_ENTER("fork", "%s", "");
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_getpriority(int which, int who) {
  ARC_STRACE_ENTER("getpriority", "%d, %d", which, who);
  if (which == PRIO_PROCESS) {
    int result = PriorityMap::GetInstance()->GetPriority(who);
    ARC_STRACE_RETURN(result);
  }
  errno = ESRCH;
  ARC_STRACE_RETURN(-1);
}

int __wrap_getrlimit(int resource, struct rlimit *rlim) {
  // TODO(crbug.com/241955): Stringify |resource| and |rlim|.
  ARC_STRACE_ENTER("getrlimit", "%d, %p", resource, rlim);
  int result = -1;
  static const uint32_t kArcRLimInfinity = -1;
  switch (resource) {
    case RLIMIT_AS:
    case RLIMIT_DATA:
      rlim->rlim_cur = kArcRLimInfinity;
      rlim->rlim_max = kArcRLimInfinity;
      result = 0;
      break;
    case RLIMIT_CORE:
    case RLIMIT_MEMLOCK:
    case RLIMIT_MSGQUEUE:
    case RLIMIT_RTPRIO:
    case RLIMIT_RTTIME:
      rlim->rlim_cur = 0;
      rlim->rlim_max = 0;
      result = 0;
      break;
    case RLIMIT_CPU:
    case RLIMIT_FSIZE:
    case RLIMIT_LOCKS:
    case RLIMIT_NICE:
    case RLIMIT_NPROC:
    case RLIMIT_RSS:
    case RLIMIT_SIGPENDING:
    case RLIMIT_STACK:
      rlim->rlim_cur = kArcRLimInfinity;
      rlim->rlim_max = kArcRLimInfinity;
      result = 0;
      break;
    case RLIMIT_NOFILE:
      // The same as in posix_translation/fd_to_file_stream_map.h
      rlim->rlim_cur = FD_SETSIZE;
      rlim->rlim_max = FD_SETSIZE;
      result = 0;
      break;
    default:
      ALOGE("Unknown getrlimit request. resource=%d", resource);
      errno = EINVAL;
      result = -1;
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_kill(pid_t pid, int sig) {
  // Although POSIX does not require it, Bionic's strsignal implementation
  // uses a buffer returned by pthread_getspecific, and hence thread-safe
  // even when |sig| is out-of-range.
  ARC_STRACE_ENTER("kill", "%d, \"%s\"",
                     static_cast<int>(pid), strsignal(sig));
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

/* Android uses madvise to hint to the kernel about what ashmem regions can be
 * deleted, and TcMalloc uses it to hint about returned system memory.  We won't
 * have this functionality in NaCl and errors returned from this function result
 * in useless debug spew, so just stub it out and ignore the advice.
 */
int __wrap_madvise(void* addr, size_t length, int advice) {
  ARC_STRACE_ENTER("madvise", "%p, %zu, %d", addr, length, advice);
  /* TODO(elijahtaylor): Eventually we should be tracking mmap calls and will
   * know which regions are file backed or not, so we could at that point zero
   * out non-file backed regions when MADV_DONTNEED is passed in, or potentially
   * follow other advice (e.g., MADV_REMOVE).
   */
  ARC_STRACE_RETURN(0);
}

int __wrap_pthread_kill(pthread_t thread, int sig) {
  ARC_STRACE_ENTER("pthread_kill", "\"%s\"", strsignal(sig));
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_setpriority(int which, int who, int prio) {
  ARC_STRACE_ENTER("setpriority", "%d, %d, %d", which, who, prio);
  if (which == PRIO_PROCESS) {
    if (prio < 0) {
      // Warn when Android or apps attempt to use higher thread priorities.
      DANGERF("Called for tid %d prio %d", who, prio);
    }
    if (who == -1) {
      // For CtsOsTestCases's ProcessTest.testMiscMethods().
      errno = ESRCH;
      ARC_STRACE_RETURN(-1);
    }
    if (prio < ANDROID_PRIORITY_HIGHEST)
      prio = ANDROID_PRIORITY_HIGHEST;  // CTS tests expect successful result.
    PriorityMap::GetInstance()->SetPriority(who, prio);
    ARC_STRACE_RETURN(0);
  }
  ALOGW("Only PRIO_PROCESS is supported in setpriority()");
  errno = EPERM;
  ARC_STRACE_RETURN(-1);
}

int __wrap_setrlimit(int resource, const struct rlimit *rlim) {
  // TODO(crbug.com/241955): Stringify |resource| and |rlim|.
  ARC_STRACE_ENTER("setrlimit", "%d, %p", resource, rlim);
  errno = EPERM;
  ARC_STRACE_RETURN(-1);
}

int __wrap_sigaction(int signum, const struct sigaction *act,
                     struct sigaction *oldact) {
  ARC_STRACE_ENTER("sigaction", "\"%s\", %p, %p",
                     strsignal(signum), act, oldact);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_tgkill(int tgid, int tid, int sig) {
  ARC_STRACE_ENTER("tgkill", "%d, %d, \"%s\"", tgid, tid, strsignal(sig));
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_tkill(int tid, int sig) {
  ARC_STRACE_ENTER("tkill", "%d, \"%s\"", tid, strsignal(sig));
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_uname(struct utsname* buf) {
  ARC_STRACE_ENTER("uname", "%p", buf);
  // Dalvik VM calls this.
  strcpy(buf->sysname, "nacl");  // NOLINT(runtime/printf)
  strcpy(buf->nodename, "localhost");  // NOLINT(runtime/printf)
  strcpy(buf->release, "31");  // NOLINT(runtime/printf)
  strcpy(buf->version, "31");  // NOLINT(runtime/printf)
  strcpy(buf->machine, "nacl");  // NOLINT(runtime/printf)
#ifdef _GNU_SOURCE
  strcpy(buf->domainname, "chrome");  // NOLINT(runtime/printf)
#endif
  ARC_STRACE_RETURN(0);
}

int __wrap_vfork() {
  ARC_STRACE_ENTER("vfork", "%s", "");
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

pid_t __wrap_wait(int *status) {
  ARC_STRACE_ENTER("wait", "%p", status);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

pid_t __wrap_waitpid(pid_t pid, int *status, int options) {
  ARC_STRACE_ENTER("waitpid", "%d, %p, %d",
                     static_cast<int>(pid), status, options);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

int __wrap_waitid(idtype_t idtype, id_t id, siginfo_t *infop, int options) {
  ARC_STRACE_ENTER("waitid", "%d, %d, %p, %d",
                     static_cast<int>(idtype), static_cast<int>(id),
                     infop, options);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

pid_t __wrap_wait3(int *status, int options, struct rusage *rusage) {
  ARC_STRACE_ENTER("wait3", "%p, %d, %p", status, options, rusage);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

pid_t __wrap_wait4(pid_t pid, int *status, int options, struct rusage *rusage) {
  ARC_STRACE_ENTER("wait4", "%d, %p, %d, %p",
                     static_cast<int>(pid), status, options, rusage);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}
