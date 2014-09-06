// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// PID and thread management functions.

#undef LOG_TAG
#define LOG_TAG "ProcessEmulator"

#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

#include <cstddef>
#include <vector>

#include "base/memory/singleton.h"
#include "common/arc_strace.h"
#include "common/alog.h"
#include "common/process_emulator.h"
#include "common/plugin_handle.h"
#include "common/scoped_pthread_mutex_locker.h"

#define real_getpid_func __real_getpid
#define wrap_getpid_func __wrap_getpid
#define wrap_getuid_func __wrap_getuid
#define real_pthread_create_func __real_pthread_create
#define wrap_pthread_create_func __wrap_pthread_create

static pthread_mutex_t s_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_key_t s_tls = 0;
static pthread_once_t s_tls_init = PTHREAD_ONCE_INIT;
static pid_t s_prev_pid = 200;
static bool s_is_multi_threaded = false;
// By default, we pretend to be a system user. This is necessary for
// dexopt because dexopt does not initialize the thread state and it
// needs to write files to system directories such as /data/dalvik-cache.
static uid_t s_fallback_uid = arc::kSystemUid;

// UID has to be at least 1000. Binder_restoreCallingIdentity enforces
// that UID is at least 1000 citing that "In Android currently there
// are no uids in this range".
static const uid_t kMinUid = 1000;

namespace arc {

namespace {

struct EmulatedProcessInfo {
  EmulatedProcessInfo(pid_t p, uid_t u)
      : pid(p), uid(u) {}

  pid_t pid;
  uid_t uid;
};

// Stores information about the change made for a Binder call.
// The caller pid/uid will be restored when call returns.
class EmulatedBinderMethodFrame {
 public:
  EmulatedBinderMethodFrame(const EmulatedProcessInfo& caller,
                            bool has_cookie, int64_t cookie)
      : caller_(caller), has_cookie_(has_cookie), cookie_(cookie) {}

  inline const EmulatedProcessInfo& GetCaller() const { return caller_; }
  inline bool HasCookie() const { return has_cookie_; }
  inline int64_t GetCookie() const { return cookie_; }

 private:
  EmulatedProcessInfo caller_;
  bool has_cookie_;
  int64_t cookie_;
};

class ProcessEmulatorThreadState {
 public:
  explicit ProcessEmulatorThreadState(const EmulatedProcessInfo& process)
      : process_(process), thread_creation_process_(process) {}

  inline EmulatedProcessInfo GetProcess() const { return process_; }

  inline pid_t GetCurrentPid() const { return process_.pid; }
  inline uid_t GetCurrentUid() const { return process_.uid; }

  inline EmulatedProcessInfo GetAndClearThreadCreationProcess() {
    EmulatedProcessInfo result = thread_creation_process_;
    thread_creation_process_ = process_;
    return result;
  }

  // Ensures that next thread creation will use provided process.
  inline void SetNextThreadEmulatedProcess(const EmulatedProcessInfo& process) {
    thread_creation_process_ = process;
  }

  inline bool HasSetNextThreadEmulatedProcess() const {
    return thread_creation_process_.pid != process_.pid;
  }

  // Stores Binder call data in the stack, updating current pid/uid
  // to the new value at the same time.
  void PushBinderFrame(
      const EmulatedProcessInfo& new_process, bool has_cookie, int64_t cookie);

  // Pops Binder call data from the stack, updating current pid/uid
  // to the original value from PushBinderFrame(). Returns true if we had
  // a EnterBinderFunc call and thus have a 'cookie'.
  bool PopBinderFrame(int64_t* cookie);

 private:
  EmulatedProcessInfo process_;
  EmulatedProcessInfo thread_creation_process_;
  std::vector<EmulatedBinderMethodFrame> binder_frames_;
};

void ProcessEmulatorThreadState::PushBinderFrame(
    const EmulatedProcessInfo& new_process,
    bool has_cookie, int64_t cookie) {
  binder_frames_.push_back(
      EmulatedBinderMethodFrame(process_, has_cookie, cookie));
  process_ = new_process;
  thread_creation_process_ = process_;
}

bool ProcessEmulatorThreadState::PopBinderFrame(int64_t* cookie) {
  const EmulatedBinderMethodFrame& frame = binder_frames_.back();
  process_ = frame.GetCaller();
  thread_creation_process_ = process_;
  bool has_cookie = frame.HasCookie();
  if (has_cookie)
    *cookie = frame.GetCookie();
  binder_frames_.pop_back();  // Destroys 'frame' object
  return has_cookie;
}

}  // namespace

volatile ProcessEmulator::EnterBinderFunc
    ProcessEmulator::binder_enter_function_ = NULL;
volatile ProcessEmulator::ExitBinderFunc
    ProcessEmulator::binder_exit_function_ = NULL;

bool IsAppUid(uid_t uid) {
  return uid >= kFirstAppUid;
}

ProcessEmulator* ProcessEmulator::GetInstance() {
  return Singleton<ProcessEmulator,
      LeakySingletonTraits<ProcessEmulator> >::get();
}

bool ProcessEmulator::IsMultiThreaded() {
  return s_is_multi_threaded;
}

// For testing.
void ProcessEmulator::SetIsMultiThreaded(bool is_multi_threaded) {
  s_is_multi_threaded = is_multi_threaded;
}

// For testing.
void ProcessEmulator::SetFallbackUidForTest(uid_t uid) {
  s_fallback_uid = uid;
}

ProcessEmulator::ProcessEmulator() {
}

static pid_t AllocateNewPid() {
  pid_t result;
  ScopedPthreadMutexLocker lock(&s_mutex);
  // We normally have 2 emulated pid values per OS process.
  ALOG_ASSERT(s_prev_pid < 0x7FFFFFFF, "Too many emulated pid values");
  result = ++s_prev_pid;
  return result;
}

static void ThreadDestroyed(void* st) {
  if (st != NULL) {
    ProcessEmulatorThreadState* thread =
        reinterpret_cast<ProcessEmulatorThreadState*>(st);
    delete thread;
  }
}

static void InitializeTls() {
  if (pthread_key_create(&s_tls, ThreadDestroyed) != 0) {
    LOG_FATAL("Unable to create TLS key");
  }
}

static ProcessEmulatorThreadState* GetThreadState() {
  pthread_once(&s_tls_init, InitializeTls);
  ProcessEmulatorThreadState* result =
      reinterpret_cast<ProcessEmulatorThreadState*>(pthread_getspecific(s_tls));
  return result;
}

static void InitThreadInternal(const EmulatedProcessInfo& process) {
  pthread_once(&s_tls_init, InitializeTls);
  if (NULL != pthread_getspecific(s_tls)) {
    LOG_FATAL("Thread already has ProcessEmulatorThreadState");
  }
  ProcessEmulatorThreadState* state = new ProcessEmulatorThreadState(process);
  if (pthread_setspecific(s_tls, state) != 0) {
    LOG_FATAL("Could not set ProcessEmulatorThreadState");
  }
}

static EmulatedProcessInfo CreateNewEmulatedProcess(uid_t uid) {
  pid_t pid = AllocateNewPid();
  return EmulatedProcessInfo(pid, uid);
}

void ProcessEmulator::CreateEmulatedProcess(uid_t uid) {
  EmulatedProcessInfo process = CreateNewEmulatedProcess(uid);
  InitThreadInternal(process);
}

pid_t ProcessEmulator::PrepareNewEmulatedProcess(uid_t uid) {
  // Note: We allow a uid of zero here only because we need to support creating
  // a privileged emulated ADB shell process at startup, which needs to
  // subsequently launch instrumentations (tests) as root, to match the behavior
  // of doing so on a stock Android device.
  if (uid != 0 && uid < kMinUid) {
    LOG_FATAL("Invalid UID");
  }
  ProcessEmulatorThreadState* state = GetThreadState();
  LOG_FATAL_IF(state == NULL, "This thread is not in an emulated process");
  if (state->HasSetNextThreadEmulatedProcess()) {
    LOG_FATAL("Second attempt to call SetNextThreadEmulatedProcess()");
  }
  EmulatedProcessInfo process = CreateNewEmulatedProcess(uid);
  state->SetNextThreadEmulatedProcess(process);
  return process.pid;
}

extern "C" pid_t real_getpid_func();

pid_t ProcessEmulator::GetRealPid() {
  return real_getpid_func();
}

// static
uid_t ProcessEmulator::GetUid() {
  ProcessEmulatorThreadState* state = GetThreadState();
  uid_t result;
  if (!state)
    result = s_fallback_uid;
  else
    result = state->GetCurrentUid();
  return result;
}

static void GetCurrentPidAndUid(
    ProcessEmulatorThreadState* state, pid_t* pid, uid_t* uid) {
  if (state != NULL) {
    *pid = state->GetCurrentPid();
    *uid = state->GetCurrentUid();
  } else {
    *pid = real_getpid_func();
    *uid = s_fallback_uid;
  }
}

void ProcessEmulator::SetBinderEmulationFunctions(
    EnterBinderFunc enterFunc, ExitBinderFunc exitFunc) {
  LOG_ALWAYS_FATAL_IF(enterFunc == NULL || exitFunc == NULL);
  LOG_ALWAYS_FATAL_IF(
      binder_enter_function_ != NULL || binder_exit_function_ != NULL);

  // 32-bit writes are atomic on all target architectures. Set "exitFunc"
  // first to make sure it is visible to whoever starts using enterFunc.
  binder_exit_function_ = exitFunc;
  binder_enter_function_ = enterFunc;
}

int64_t ProcessEmulator::GetPidToken() {
  pid_t pid;
  uid_t uid;
  ProcessEmulatorThreadState* state = GetThreadState();
  GetCurrentPidAndUid(state, &pid, &uid);
  return ((int64_t) pid << 32) | uid;
}

bool ProcessEmulator::EnterBinderCall(int64_t pidToken) {
  ProcessEmulatorThreadState* state = GetThreadState();
  if (state == NULL) {
    ALOGW("Detected a Binder call on a thread with no emulated process");
    return false;
  }

  pid_t caller_pid;
  uid_t caller_uid;
  GetCurrentPidAndUid(state, &caller_pid, &caller_uid);

  pid_t callee_pid = (pid_t) ((pidToken >> 32) & 0xFFFFFFFF);
  uid_t callee_uid = (uid_t) (pidToken & 0xFFFFFFFF);

  if (caller_pid == callee_pid && caller_uid == callee_uid) {
    // Same process - no need to update caller info or pid.
    return false;
  }
  if (caller_pid == callee_pid && caller_uid != callee_uid) {
    ALOGE("Binder call UID mismatch, was %d now %d, pid %d",
          caller_uid, callee_uid, caller_pid);
  }

  // ALOGV("Switching from pid %d to %d", caller_pid, callee_pid);
  EmulatedProcessInfo new_process(callee_pid, callee_uid);
  if (binder_enter_function_ != NULL) {
    int64_t cookie = (*binder_enter_function_)();
    state->PushBinderFrame(new_process, true, cookie);
  } else {
    state->PushBinderFrame(new_process, false, 0);
  }

  return true;
}

void ProcessEmulator::ExitBinderCall() {
  ProcessEmulatorThreadState* state = GetThreadState();
  // 'state' is not NULL since it was checked in EnterBinderCall().

  int64_t cookie = 0;
  bool has_cookie = state->PopBinderFrame(&cookie);
  // ALOGV("Switched to pid %d", getpid());
  if (has_cookie && binder_exit_function_ != NULL) {
    (*binder_exit_function_)(cookie);
  }
}

extern "C" int real_pthread_create_func(
    pthread_t* thread_out,
    pthread_attr_t const* attr,
    void* (*start_routine)(void*),  // NOLINT(readability/casting)
    void* arg);

extern "C" pid_t wrap_getpid_func() {
  ARC_STRACE_ENTER("getpid", "%s", "");
  ProcessEmulatorThreadState* state = GetThreadState();
  pid_t result;
  if (!state)
    result = real_getpid_func();
  else
    result = state->GetCurrentPid();
  ARC_STRACE_RETURN(result);
}

extern "C" uid_t wrap_getuid_func() {
  ARC_STRACE_ENTER("getuid", "%s", "");
  const uid_t result = ProcessEmulator::GetUid();
  ARC_STRACE_RETURN(result);
}

class ThreadCreateArg {
 public:
  ThreadCreateArg(EmulatedProcessInfo process,
                  void* (*start_routine)(void*),  // NOLINT(readability/casting)
                  void* arg)
      : process_(process), start_routine_(start_routine), arg_(arg) {}

  EmulatedProcessInfo process_;
  void* (*start_routine_)(void*);  // NOLINT
  void* arg_;
};

static void* thread_start_wrapper(void* arg) {
  ThreadCreateArg* wrapped_arg = reinterpret_cast<ThreadCreateArg*>(arg);
  InitThreadInternal(wrapped_arg->process_);
  void* (*original_start_routine)(void*) =  // NOLINT
      wrapped_arg->start_routine_;
  void* original_arg = wrapped_arg->arg_;
  delete wrapped_arg;

  static int estimated_threads = 0;
  ++estimated_threads;
  ARC_STRACE_REPORT("Approximately %d threads (new thread) func=%p arg=%p",
                      estimated_threads, original_start_routine, original_arg);
  ALOGI("Approximately %d threads (new thread)", estimated_threads);
  void* result = original_start_routine(original_arg);
  ALOGI("Approximately %d threads (thread done)", estimated_threads);
  ARC_STRACE_REPORT("Approximately %d threads (thread done) result=%p",
                      estimated_threads, result);
  --estimated_threads;

  return result;
}

// Bionic's thread stack size default is 1MB.
#define DEFAULT_STACK_SIZE  1024 * 1024

#define CHECK_PTHREAD(call)  { \
    int result = call; \
    LOG_ALWAYS_FATAL_IF(result != 0, "pthread call failed: %d (%s)\n", \
                        result, #call); }

static bool update_default_stack_size(
    pthread_attr_t const* src_attr, pthread_attr_t* dst_attr) {
  size_t stack_size = 0;
  if (src_attr != NULL) {
    void* stack_addr = NULL;
    CHECK_PTHREAD(pthread_attr_getstack(src_attr, &stack_addr, &stack_size));

    if (stack_addr != NULL) {
      ALOGW("Thread creator has set stack address=%p, size=%d. "
            "Note that this is not safe.", stack_addr, stack_size);
      return false;
    }

    if (stack_size != 0) {
      // Thread creator requested a specific stack size.
      // Use the original thread creation attributes.
      return false;
    }

    // Ignoring pthread_attr_setaffinity_np as it is not supported in NaCl.

    int detachstate = PTHREAD_CREATE_JOINABLE;
    if (pthread_attr_getdetachstate(src_attr, &detachstate) == 0) {
      CHECK_PTHREAD(pthread_attr_setdetachstate(dst_attr, detachstate));
    }

    struct sched_param schedparam = {};
    if (pthread_attr_getschedparam(src_attr, &schedparam) == 0) {
      CHECK_PTHREAD(pthread_attr_setschedparam(dst_attr, &schedparam));
    }

    int schedpolicy = SCHED_OTHER;
    if (pthread_attr_getschedpolicy(src_attr, &schedpolicy) == 0) {
      CHECK_PTHREAD(pthread_attr_setschedpolicy(dst_attr, schedpolicy));
    }

    size_t guardsize = 0;
    if (pthread_attr_getguardsize(src_attr, &guardsize) == 0) {
      CHECK_PTHREAD(pthread_attr_setguardsize(dst_attr, guardsize));
    }
  }

  CHECK_PTHREAD(pthread_attr_setstacksize(dst_attr, DEFAULT_STACK_SIZE));
  return true;
}

static int call_real_pthread_create(
    pthread_t* thread_out,
    pthread_attr_t const* attr,
    void* (*start_routine)(void*),  // NOLINT(readability/casting)
    void* arg) {
  int result;
  ProcessEmulatorThreadState* state = GetThreadState();
  if (state == NULL) {
    result = real_pthread_create_func(
        thread_out, attr, start_routine, arg);
  } else {
    EmulatedProcessInfo process = state->GetAndClearThreadCreationProcess();
    ThreadCreateArg* wrapped_arg =
        new ThreadCreateArg(process, start_routine, arg);
    result = real_pthread_create_func(
        thread_out, attr, &thread_start_wrapper, wrapped_arg);
  }
  return result;
}

// Intercept all pthread_create() calls and set up emulated uid and pid
// values of the created thread.
extern "C" int wrap_pthread_create_func(
    pthread_t* thread_out,
    pthread_attr_t const* attr,
    void* (*start_routine)(void*),  // NOLINT(readability/casting)
    void* arg) {
  // TODO(crbug.com/241955): Stringify |attr|?
  ARC_STRACE_ENTER("pthread_create", "%p, %p, %p, %p",
                     thread_out, attr, start_routine, arg);

  // A mutex lock is not necessary here since real_pthread_create_func() itself
  // is a memory barrier. It is ensured by real_pthread_create_func() that the
  // |start_routine| can always see the new |s_is_multi_threaded| value. Note
  // that Bionic's pthread_create() in android/bionic/libc/bionic/pthread.c has
  // a very similar variabled called __isthreaded, and the variable is updated
  // without a lock.
  s_is_multi_threaded = true;

  pthread_attr_t thread_attr;
  pthread_attr_init(&thread_attr);
  int result;
  if (update_default_stack_size(attr, &thread_attr)) {
    result = call_real_pthread_create(
        thread_out, &thread_attr, start_routine, arg);
  } else {
    result = call_real_pthread_create(
        thread_out, attr, start_routine, arg);
  }
  pthread_attr_destroy(&thread_attr);
  ARC_STRACE_RETURN(result);
}

}  // namespace arc
