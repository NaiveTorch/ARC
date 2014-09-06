/* Copyright 2014 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Wrappers for various file system calls.
 */

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <nacl_stat.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/vfs.h>
#include <unistd.h>
#include <utime.h>

#include <string>
#include <vector>

#include "base/basictypes.h"
#include "base/safe_strerror_posix.h"
#include "base/strings/string_piece.h"
#include "base/strings/string_util.h"
#include "common/arc_strace.h"
#include "common/alog.h"
#include "common/danger.h"
#include "common/dlfcn_injection.h"
#include "common/file_util.h"
#include "common/logd_write.h"
#include "common/memory_state.h"
#include "common/options.h"
#include "common/plugin_handle.h"
#include "common/thread_local.h"
#include "common/trace_event.h"
#include "common/virtual_file_system_interface.h"
#include "wrap/file_wrap_private.h"
#include "wrap/libc_dispatch_table.h"

#if !defined(LIBWRAP_FOR_TEST)
// A macro to wrap an IRT function. Note that the macro does not wrap IRT
// calls made by the Bionic loader. For example, wrapping mmap with DO_WRAP
// does not hook the mmap IRT calls in phdr_table_load_segments() in
// mods/android/bionic/linker/linker_phdr.c. This is because the loader has
// its own set of IRT function pointers that are not visible from non-linker
// code.
#define DO_WRAP(name)                                   \
  __nacl_irt_ ## name ## _real = __nacl_irt_ ## name;   \
  __nacl_irt_ ## name  = __nacl_irt_ ## name ## _wrap
#else
// For testing, just set up the _real variables.
#define DO_WRAP(name)                                   \
  __nacl_irt_ ## name ## _real = __nacl_irt_ ## name;
#endif

// A macro to define an IRT wrapper and a function pointer to store
// the real IRT function.
#define IRT_WRAPPER(name, ...)                              \
  extern int (*__nacl_irt_ ## name)(__VA_ARGS__);           \
  static int (*__nacl_irt_ ## name ## _real)(__VA_ARGS__);  \
  int (__nacl_irt_ ## name ## _wrap)(__VA_ARGS__)

// Note about large file support in ARC:
//
// Unlike glibc, Bionic does not support _LARGEFILE64_SOURCE and
// _FILE_OFFSET_BITS=64 macros. Instead, it always provides both foo() and
// foo64() functions. It is user code's responsibility to call foo64()
// explicitly instead of foo() when large file support is necessary.
// Note that Android's JNI code properly calls these 64-bit variants.
//
// For Bionic, we should provide both
//    __wrap_foo(type_t param1, another_type_t param2);
// and
//    __wrap_foo64(type64_t param1, another_type64_t param2);
// functions because both could be called.

extern "C" {
// sorted by syscall name.
int __wrap_access(const char* pathname, int mode);
int __wrap_chdir(const char* path);
int __wrap_chown(const char* path, uid_t owner, gid_t group);
int __wrap_dlclose(const void* handle);
void* __wrap_dlopen(const char* filename, int flag);
void* __wrap_dlsym(const void* handle, const char* symbol);
char* __wrap_getcwd(char* buf, size_t size);
int __wrap_getdents(
    unsigned int fd, struct dirent* dirp, unsigned int count);
int __wrap_mkdir(const char* pathname, mode_t mode);
char* __wrap_mkdtemp(char* tmpl);
int __wrap_mkstemp(char* tmpl);
int __wrap_mkstemps(char* tmpl, int suffix_len);
int __wrap_open(const char* pathname, int flags, ...);
ssize_t __wrap_readlink(const char* path, char* buf, size_t bufsiz);
char* __wrap_realpath(const char* path, char* resolved_path);
int __wrap_remove(const char* pathname);
int __wrap_rename(const char* oldpath, const char* newpath);
int __wrap_rmdir(const char* pathname);
int __wrap_stat(const char* filename, struct stat* buf);
int __wrap_statfs(const char* path, struct statfs* stat);
int __wrap_statvfs(const char* path, struct statvfs* stat);
FILE* __wrap_tmpfile();
mode_t __wrap_umask(mode_t mask);
int __wrap_unlink(const char* pathname);
int __wrap_utime(const char* filename, const struct utimbuf* times);
int __wrap_utimes(const char* filename, const struct timeval times[2]);

extern int __real_access(const char* pathname, int mode);
extern int __real_dlclose(const void* handle);
extern void* __real_dlopen(const char* filename, int flag);
extern void* __real_dlsym(const void* handle, const char* symbol);
extern char* __real_getcwd(char* buf, size_t size);
extern int __real_mkdir(const char* pathname, mode_t mode);
extern int __real_open(const char* pathname, int flags, mode_t mode);
extern ssize_t __real_readlink(const char* path, char* buf, size_t bufsiz);
extern char* __real_realpath(const char* path, char* resolved_path);
extern int __real_remove(const char* pathname);
extern int __real_rename(const char* oldpath, const char* newpath);
extern int __real_rmdir(const char* pathname);
extern int __real_stat(const char* filename, struct stat* buf);
extern int __real_statfs(const char* filename, struct statfs* buf);
extern int __real_statvfs(const char* filename, struct statvfs* buf);
extern int __real_unlink(const char* pathname);

// Bionic's off_t is 32bit but bionic also provides 64 bit version of
// functions which take off64_t. We need to define the wrapper of
// the 64 bit versions as well.
int __wrap_ftruncate(int fd, off_t length);
off_t __wrap_lseek(int fd, off_t offset, int whence);
int __wrap_truncate(const char* path, off_t length);

int __wrap_ftruncate64(int fd, off64_t length);
off64_t __wrap_lseek64(int fd, off64_t offset, int whence);
ssize_t __wrap_pread(int fd, void* buf, size_t count, off_t offset);
ssize_t __wrap_pwrite(int fd, const void* buf, size_t count, off_t offset);
ssize_t __wrap_pread64(int fd, void* buf, size_t count, off64_t offset);
ssize_t __wrap_pwrite64(int fd, const void* buf, size_t count, off64_t offset);
int __wrap_truncate64(const char* path, off64_t length);

// To simplify the implementation, we always use 64 bit version when we fall
// back to the real implementation.
extern int __real_ftruncate64(int fd, off64_t length);
extern off64_t __real_lseek64(int fd, off64_t offset, int whence);
extern ssize_t __real_pread64(int fd, void* buf, size_t count, off64_t offset);
extern ssize_t __real_pwrite64(
    int fd, const void* buf, size_t count, off64_t offset);

// sorted by syscall name.
int __wrap_close(int fd);
int __wrap_creat(const char* pathname, mode_t mode);
int __wrap_dup(int oldfd);
int __wrap_dup2(int oldfd, int newfd);
int __wrap_fcntl(int fd, int cmd, ...);
FILE* __wrap_fdopen(int fildes, const char* mode);
int __wrap_flock(int fd, int operation);
int __wrap_ioctl(int fd, int request, ...);
void* __wrap_mmap(
    void* addr, size_t length, int prot, int flags, int fd, off_t offset);
int __wrap_mprotect(const void* addr, size_t length, int prot);
int __wrap_munmap(void* addr, size_t length);
int __wrap_poll(struct pollfd* fds, nfds_t nfds, int timeout);
ssize_t __wrap_read(int fd, void* buf, size_t count);
ssize_t __wrap_readv(int fd, const struct iovec* iov, int iovcnt);
ssize_t __wrap_write(int fd, const void* buf, size_t count);
ssize_t __wrap_writev(int fd, const struct iovec* iov, int iovcnt);

extern int __real_close(int fd);
extern int __real_dup(int oldfd);
extern int __real_fdatasync(int fd);
extern int __real_fstat(int fd, struct stat *buf);
extern int __real_fsync(int fd);
extern void* __real_mmap(
    void* addr, size_t length, int prot, int flags, int fd, off_t offset);
extern int __real_mprotect(const void* addr, size_t length, int prot);
extern int __real_munmap(void* addr, size_t length);
extern int __real_munlock(const void* addr, size_t len);
extern int __real_munlockall();
extern int __real_poll(struct pollfd* fds, nfds_t nfds, int timeout);
extern ssize_t __real_read(int fd, void* buf, size_t count);
extern ssize_t __real_readv(int fd, const struct iovec* iov, int count);
extern mode_t __real_umask(mode_t mask);
extern ssize_t __real_write(int fd, const void* buf, size_t count);
extern ssize_t __real_writev(int fd, const struct iovec* iov, int count);

int __wrap_lstat(const char* path, struct stat* buf);
int __wrap_stat(const char* filename, struct stat* buf);
extern int __real_lstat(const char* path, struct stat* buf);
extern int __real_stat(const char* filename, struct stat* buf);
}  // extern "C"

namespace {

// Counts the depth of __wrap_write() calls to avoid infinite loop back.
DEFINE_THREAD_LOCAL(int, g_wrap_write_nest_count);

// Helper function for converting from nacl_abi_stat to stat.
void NaClAbiStatToStat(struct nacl_abi_stat* nacl_stat, struct stat* st) {
  st->st_dev = nacl_stat->nacl_abi_st_dev;
  st->st_mode = nacl_stat->nacl_abi_st_mode;
  st->st_nlink = nacl_stat->nacl_abi_st_nlink;
  st->st_uid = nacl_stat->nacl_abi_st_uid;
  st->st_gid = nacl_stat->nacl_abi_st_gid;
  st->st_rdev = nacl_stat->nacl_abi_st_rdev;
  st->st_size = nacl_stat->nacl_abi_st_size;
  st->st_blksize = nacl_stat->nacl_abi_st_blksize;
  st->st_blocks = nacl_stat->nacl_abi_st_blocks;
  st->st_atime = nacl_stat->nacl_abi_st_atime;
  st->st_atime_nsec = 0;
  st->st_mtime = nacl_stat->nacl_abi_st_mtime;
  st->st_mtime_nsec = 0;
  st->st_ctime = nacl_stat->nacl_abi_st_ctime;
  st->st_ctime_nsec = 0;
  st->st_ino = nacl_stat->nacl_abi_st_ino;
}

// Helper function for converting from stat to nacl_abi_stat.
void StatToNaClAbiStat(struct stat* st, struct nacl_abi_stat* nacl_stat) {
  nacl_stat->nacl_abi_st_dev = st->st_dev;
  nacl_stat->nacl_abi_st_mode= st->st_mode;
  nacl_stat->nacl_abi_st_nlink = st->st_nlink;
  nacl_stat->nacl_abi_st_uid = st->st_uid;
  nacl_stat->nacl_abi_st_gid = st->st_gid;
  nacl_stat->nacl_abi_st_rdev = st->st_rdev;
  nacl_stat->nacl_abi_st_size = st->st_size;
  nacl_stat->nacl_abi_st_blksize = st->st_blksize;
  nacl_stat->nacl_abi_st_blocks = st->st_blocks;
  nacl_stat->nacl_abi_st_atime = st->st_atime;
  nacl_stat->nacl_abi_st_mtime = st->st_mtime;
  nacl_stat->nacl_abi_st_ctime = st->st_ctime;
  nacl_stat->nacl_abi_st_ino = st->st_ino;
}

}  // namespace

namespace arc {

/* Android libraries often try to load files from /system, but that does not
 * exist on our host systems.  Since we don't want to modify Android libraries,
 * instead intercept the open calls and redirect them to ANDROID_ROOT where all
 * our data is housed.
 */
std::string GetAndroidRoot() {
  return "/system";
}

VirtualFileSystemInterface* GetFileSystem() {
#if !defined(LIBWRAP_FOR_TEST)
  arc::PluginHandle handle;
  VirtualFileSystemInterface* file_system = handle.GetVirtualFileSystem();
  ALOG_ASSERT(file_system);
  return file_system;
#else
  return NULL;
#endif
}

}  // namespace arc

using arc::GetFileSystem;
using arc::VirtualFileSystemInterface;

// sorted by syscall name.

int __wrap_access(const char* pathname, int mode) {
  ARC_STRACE_ENTER("access", "\"%s\", %s",
                     SAFE_CSTR(pathname),
                     arc::GetAccessModeStr(mode).c_str());
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    result = file_system->access(pathname, mode);
  } else {
    std::string newpath(pathname);
    result = __real_access(newpath.c_str(), mode);
  }
  if (result == -1 && errno != ENOENT) {
    DANGERF("path=%s mode=%d: %s",
            SAFE_CSTR(pathname), mode, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_chdir(const char* path) {
  ARC_STRACE_ENTER("chdir", "\"%s\"", SAFE_CSTR(path));
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    result = file_system->chdir(path);
  } else {
    DANGERF("chdir: not supported");
    errno = ENOSYS;
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_chown(const char* path, uid_t owner, gid_t group) {
  ARC_STRACE_ENTER("chown", "\"%s\", %u, %u", SAFE_CSTR(path), owner, group);
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->chown(path, owner, group);
  else
    errno = ENOSYS;
  ARC_STRACE_RETURN(result);
}

int __wrap_dlclose(const void* handle) {
  // TODO(crbug.com/241955): Decipher |handle|
  ARC_STRACE_ENTER("dlclose", "%p", handle);
  int result = __real_dlclose(handle);
  // false since dlclose never sets errno.
  ARC_STRACE_RETURN_INT(result, false);
}

void* __wrap_dlopen(const char* filename, int flag) {
  ARC_STRACE_ENTER("dlopen", "\"%s\", %s",
                     SAFE_CSTR(filename),
                     arc::GetDlopenFlagStr(flag).c_str());
  void* result = NULL;
  // __real_dlopen is known to be slow under NaCl.
  TRACE_EVENT2(ARC_TRACE_CATEGORY, "wrap_dlopen",
               "filename", TRACE_STR_COPY(SAFE_CSTR(filename)),
               "flag", flag);
  result = __real_dlopen(filename, flag);
  if (!result && filename && filename[0] != '/') {
    // ARC statically links some libraries into the main
    // binary. When an app dlopen such library, we should return the
    // handle of the main binary so that apps can find symbols.
    if (arc::IsStaticallyLinkedSharedObject(filename)) {
      result = __real_dlopen(NULL, flag);
    }
  }
  // false since dlopen never sets errno.
  ARC_STRACE_RETURN_PTR(result, false);
}

void* __wrap_dlsym(const void* handle, const char* symbol) {
  // TODO(crbug.com/241955): Decipher |handle|
  ARC_STRACE_ENTER("dlsym", "%s, \"%s\"",
                     arc::GetDlsymHandleStr(handle).c_str(),
                     SAFE_CSTR(symbol));
  void* result = __real_dlsym(handle, symbol);
  // false since dlsym never sets errno.
  ARC_STRACE_RETURN_PTR(result, false);
}

char* __wrap_getcwd(char* buf, size_t size) {
  ARC_STRACE_ENTER("getcwd", "%p, %zu", buf, size);
  char* result = NULL;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->getcwd(buf, size);
  else
    result = __real_getcwd(buf, size);
  ARC_STRACE_REPORT("result=\"%s\"", SAFE_CSTR(result));
  ARC_STRACE_RETURN_PTR(result, false);
}

int __wrap_getdents(
    unsigned int fd, struct dirent* dirp, unsigned int count) {
  ARC_STRACE_ENTER_FD("getdents", "%d, %p, %u", fd, dirp, count);
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->getdents(fd, dirp, count);
  else
    errno = ENOSYS;
  ARC_STRACE_RETURN(result);
}

extern "C" {
IRT_WRAPPER(getcwd, char* buf, size_t size) {
  return __wrap_getcwd(buf, size) ? 0 : errno;
}
}  // extern "C"

int __wrap_lstat(const char* path, struct stat* buf) {
  ARC_STRACE_ENTER("lstat", "\"%s\", %p",
                     SAFE_CSTR(path), buf);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    result = file_system->lstat(path, buf);
  } else {
    std::string newpath(path);
    result = __real_lstat(newpath.c_str(), buf);
  }
  if (result == -1 && errno != ENOENT) {
    DANGERF("path=%s: %s",
            SAFE_CSTR(path), safe_strerror(errno).c_str());
  }
  if (!result)
    ARC_STRACE_REPORT("buf=%s", arc::GetStatStr(buf).c_str());
  ARC_STRACE_RETURN(result);
}

int __wrap_mkdir(const char* pathname, mode_t mode) {
  ARC_STRACE_ENTER("mkdir", "\"%s\", 0%o", SAFE_CSTR(pathname), mode);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->mkdir(pathname, mode);
  else
    result = __real_mkdir(pathname, mode);
  if (result == -1 && errno != EEXIST) {
    DANGERF("path=%s mode=%d: %s",
            SAFE_CSTR(pathname), mode, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

static const ssize_t kPlaceholderLen = 6;

static char* GetTemplatePlaceholder(char* tmpl, size_t size) {
  LOG_FATAL_IF(size > strlen(tmpl),
               "GetTemplateSuffix: size is too large: tmpl=\"%s\" size=%zu",
               tmpl, size);
  if (!EndsWith(std::string(tmpl, size),
                std::string(kPlaceholderLen, 'X'), true))
    return NULL;
  return tmpl + size - kPlaceholderLen;
}

static bool GenerateRandomName(char* tmpl_placeholder, int rfd) {
  static const char kFsSafeChars[] =
    "0123456789abcdefghijklmnopqrstuvwxyzxABCDEFGHIJKLMNOPQRSTUVWXYZ-_";
  static const size_t kFsSafeCharsLen = sizeof(kFsSafeChars) - 1;
  unsigned char buf[kPlaceholderLen];
  if (read(rfd, buf, kPlaceholderLen) != kPlaceholderLen)
    return false;
  for (ssize_t i = 0; i < kPlaceholderLen; ++i) {
    tmpl_placeholder[i] = kFsSafeChars[buf[i] % kFsSafeCharsLen];
  }
  return true;
}

// TODO(crbug.com/339717): We should do either of the following: (1) Use IRT
// hooks more and stop wrapping this function, or (2) reuse Bionic's almost
// as-is like opendir().
static int MkostempsImpl(char* tmpl, int suffix_len, int flags) {
  size_t tmpl_size = strlen(tmpl);
  if (suffix_len < 0 || tmpl_size < static_cast<size_t>(suffix_len)) {
    DANGERF("mkostemps: invalid template - %s %d",
            SAFE_CSTR(tmpl), suffix_len);
    errno = EINVAL;
    return -1;
  }
  static const size_t kMaxTrial = 128;
  char* tmpl_placeholder =
      GetTemplatePlaceholder(tmpl, tmpl_size - suffix_len);
  if (!tmpl_placeholder) {
    DANGERF("mkostemps: invalid template - %s %d",
            SAFE_CSTR(tmpl), suffix_len);
    errno = EINVAL;
    return -1;
  }
  int rfd = open("/dev/urandom", O_RDONLY);
  if (rfd == -1) {
    DANGERF("mkostemps: no random device");
    errno = EEXIST;
    return -1;
  }

  for (size_t n = 0; n < kMaxTrial; ++n) {
    if (!GenerateRandomName(tmpl_placeholder, rfd))
      continue;
    int fd = open(tmpl, O_RDWR | O_CREAT | O_EXCL | flags, 0600);
    if (fd < 0)
      continue;
    close(rfd);
    // No ARC_STRACE_REGISTER_FD because it was already done in open.
    return fd;
  }

  DANGERF("mkostemps: cannot create a file - %s %d", SAFE_CSTR(tmpl),
          suffix_len);
  close(rfd);
  errno = EEXIST;
  return -1;
}

// TODO(crbug.com/339717): We should do either of the following: (1) Use IRT
// hooks more and stop wrapping this function, or (2) reuse Bionic's almost
// as-is like opendir().
char* __wrap_mkdtemp(char* tmpl) {
  ARC_STRACE_ENTER("mkdtemp", "\"%s\"", SAFE_CSTR(tmpl));
  static const size_t kMaxTrial = 128;
  char* tmpl_suffix = GetTemplatePlaceholder(tmpl, strlen(tmpl));
  if (!tmpl_suffix) {
    DANGERF("mkdtemp: invalid template - %s", SAFE_CSTR(tmpl));
    errno = EINVAL;
    ARC_STRACE_RETURN_PTR(NULL, true);
  }
  int rfd = open("/dev/urandom", O_RDONLY);
  if (rfd == -1) {
    DANGERF("mkdtemp: no random device - %s", SAFE_CSTR(tmpl));
    errno = EEXIST;
    ARC_STRACE_RETURN_PTR(NULL, true);
  }

  for (size_t n = 0; n < kMaxTrial; ++n) {
    if (!GenerateRandomName(tmpl_suffix, rfd))
      continue;
    // NB: pepper_file.cc does not return -1 even when |tmpl| already exists.
    // See crbug.com/314879
    int res = mkdir(tmpl, 0700);
    if (res < 0)
      continue;
    close(rfd);
    ARC_STRACE_RETURN_PTR(tmpl, false);
  }

  DANGERF("mkdtemp: cannot create a directory - %s", SAFE_CSTR(tmpl));
  close(rfd);
  // This is not POSIX compliant. We should probably loop endlessly instead.
  errno = EEXIST;
  ARC_STRACE_RETURN_PTR(NULL, true);
}

// TODO(crbug.com/339717): We should do either of the following: (1) Use IRT
// hooks more and stop wrapping this function, or (2) reuse Bionic's almost
// as-is like opendir().
int __wrap_mkstemp(char* tmpl) {
  ARC_STRACE_ENTER("mkstemp", "\"%s\"", SAFE_CSTR(tmpl));
  int fd = MkostempsImpl(tmpl, 0, 0);
  ARC_STRACE_RETURN(fd);
}

int __wrap_mkstemps(char* tmpl, int suffix_len) {
  ARC_STRACE_ENTER("mkstemps", "\"%s\" %d", SAFE_CSTR(tmpl), suffix_len);
  int fd = MkostempsImpl(tmpl, suffix_len, 0);
  ARC_STRACE_RETURN(fd);
}

int __wrap_open(const char* pathname, int flags, ...) {
  va_list argp;
  va_start(argp, flags);
  mode_t mode = 0;
  if (flags & O_CREAT) {
    // Passing mode_t to va_arg with bionic makes compile fail.
    // As bionic's mode_t is short, the value is promoted when it was
    // passed to this vaarg function and fetching it as a short value
    // is not valid. This definition can be bad if mode_t is a 64bit
    // value, but such environment might not exist.
    COMPILE_ASSERT(sizeof(mode) <= sizeof(int),  // NOLINT(runtime/sizeof)
                   mode_t_is_too_big);
    mode = va_arg(argp, int);
  }
  va_end(argp);

  ARC_STRACE_ENTER("open", "\"%s\", %s, 0%o",
                     SAFE_CSTR(pathname),
                     arc::GetOpenFlagStr(flags).c_str(), mode);
  int fd = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    fd = file_system->open(pathname, flags, mode);
  else
    fd = __real_open(pathname, flags, mode);
  if (fd == -1 && errno != ENOENT) {
    DANGERF("pathname=%s flags=%d: %s",
            SAFE_CSTR(pathname), flags, safe_strerror(errno).c_str());
  }
  ARC_STRACE_REGISTER_FD(fd, SAFE_CSTR(pathname));
  ARC_STRACE_RETURN(fd);
}

ssize_t __wrap_readlink(const char* path, char* buf, size_t bufsiz) {
  ARC_STRACE_ENTER("readlink", "\"%s\", %p, %zu",
                     SAFE_CSTR(path), buf, bufsiz);
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->readlink(path, buf, bufsiz);
  else
    result = __real_readlink(path, buf, bufsiz);
  if (result == -1) {
    DANGERF("path=%s bufsiz=%zu: %s",
            SAFE_CSTR(path), bufsiz, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

char* __wrap_realpath(const char* path, char* resolved_path) {
  ARC_STRACE_ENTER("realpath", "\"%s\", %p", SAFE_CSTR(path), resolved_path);
  char* result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->realpath(path, resolved_path);
  else
    result = __real_realpath(path, resolved_path);
  if (!result) {
    DANGERF("path=%s resolved_path=%p: %s",
            SAFE_CSTR(path), resolved_path, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN_PTR(result, !result);
}

int __wrap_remove(const char* pathname) {
  ARC_STRACE_ENTER("remove", "\"%s\"", SAFE_CSTR(pathname));
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->remove(pathname);
  else
    result = __real_remove(pathname);
  if (result == -1 && errno != ENOENT)
    DANGERF("path=%s: %s", SAFE_CSTR(pathname), safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(result);
}

int __wrap_rename(const char* oldpath, const char* newpath) {
  ARC_STRACE_ENTER("rename", "\"%s\", \"%s\"",
                     SAFE_CSTR(oldpath), SAFE_CSTR(newpath));
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->rename(oldpath, newpath);
  else
    result = __real_rename(oldpath, newpath);
  if (result == -1) {
    DANGERF("oldpath=%s newpath=%s: %s",
            SAFE_CSTR(oldpath), SAFE_CSTR(newpath),
            safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_statfs(const char* pathname, struct statfs* stat) {
  ARC_STRACE_ENTER("statfs", "\"%s\", %p", SAFE_CSTR(pathname), stat);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->statfs(pathname, stat);
  else
    result = __real_statfs(pathname, stat);
  if (result == -1 && errno != ENOENT)
    DANGERF("path=%s: %s", SAFE_CSTR(pathname), safe_strerror(errno).c_str());
  ARC_STRACE_REPORT(
      "stat={type=%lld bsize=%lld blocks=%llu bfree=%llu bavail=%llu "
      "files=%llu ffree=%llu fsid=%d,%d namelen=%lld frsize=%lld "
      // Note: Unlike glibc and older Bionic, f_spare[] in Bionic 4.4 has
      // only 4 elements, not 5.
      "spare=%lld,%lld,%lld,%lld}",
      static_cast<int64_t>(stat->f_type),
      static_cast<int64_t>(stat->f_bsize),
      stat->f_blocks, stat->f_bfree,
      stat->f_bavail, stat->f_files, stat->f_ffree,
      stat->f_fsid.__val[0], stat->f_fsid.__val[1],
      static_cast<int64_t>(stat->f_namelen),
      static_cast<int64_t>(stat->f_frsize),
      static_cast<int64_t>(stat->f_spare[0]),
      static_cast<int64_t>(stat->f_spare[1]),
      static_cast<int64_t>(stat->f_spare[2]),
      static_cast<int64_t>(stat->f_spare[3]));
  ARC_STRACE_RETURN(result);
}

int __wrap_statvfs(const char* pathname, struct statvfs* stat) {
  ARC_STRACE_ENTER("statvfs", "\"%s\", %p", SAFE_CSTR(pathname), stat);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->statvfs(pathname, stat);
  else
    result = __real_statvfs(pathname, stat);
  ARC_STRACE_REPORT(
      "stat={bsize=%llu frsize=%llu blocks=%llu bfree=%llu bavail=%llu "
      "files=%llu ffree=%llu favail=%llu fsid=%llu flag=%llu namemax=%llu}",
      static_cast<int64_t>(stat->f_bsize),
      static_cast<int64_t>(stat->f_frsize),
      static_cast<int64_t>(stat->f_blocks),
      static_cast<int64_t>(stat->f_bfree),
      static_cast<int64_t>(stat->f_bavail),
      static_cast<int64_t>(stat->f_files),
      static_cast<int64_t>(stat->f_ffree),
      static_cast<int64_t>(stat->f_favail),
      static_cast<int64_t>(stat->f_fsid),
      static_cast<int64_t>(stat->f_flag),
      static_cast<int64_t>(stat->f_namemax));
  ARC_STRACE_RETURN(result);
}

// TODO(crbug.com/350800): Reenable 'tmpfile_fileno_fprintf_rewind_fgets' Bionic
// CTS to test this function.
// TODO(crbug.com/339717): We should do either of the following: (1) Use IRT
// hooks more and stop wrapping tmpfile, or (2) reuse Bionic's tmpfile almost
// as-is like opendir().
FILE* __wrap_tmpfile() {
  ARC_STRACE_ENTER("tmpfile", "%s", "");
  // As shown in plugin/file_system_manager.cc, /tmp/arc-provider is world-
  // writable.
  char filename[] = "/tmp/arc-provider/tmpfile-XXXXXX";
  int fd = mkstemp(filename);
  if (fd < 0)
    ARC_STRACE_RETURN_PTR(NULL, true);

  unlink(filename);
  FILE* fp = fdopen(fd, "w+b");
  if (!fp)
    close(fd);
  ARC_STRACE_RETURN_PTR(fp, !fp);
}

template <typename OffsetType>
static int TruncateImpl(const char* pathname, OffsetType length) {
  ARC_STRACE_ENTER("truncate", "\"%s\", %lld",
                     SAFE_CSTR(pathname), static_cast<int64_t>(length));
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->truncate(pathname, length);
  else
    errno = ENOSYS;
  if (result == -1) {
    DANGERF("path=%s length=%lld: %s",
            SAFE_CSTR(pathname), static_cast<int64_t>(length),
            safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_truncate(const char* pathname, off_t length) {
  return TruncateImpl(pathname, length);
}

int __wrap_truncate64(const char* pathname, off64_t length) {
  return TruncateImpl(pathname, length);
}

int __wrap_unlink(const char* pathname) {
  ARC_STRACE_ENTER("unlink", "\"%s\"", SAFE_CSTR(pathname));
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->unlink(pathname);
  else
    result = __real_unlink(pathname);
  if (result == -1 && errno != ENOENT)
    DANGERF("path=%s: %s", SAFE_CSTR(pathname), safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(result);
}

int __wrap_utimes(const char* filename, const struct timeval times[2]) {
  ARC_STRACE_ENTER("utimes", "\"%s\", %p", SAFE_CSTR(filename), times);
  int result = 0;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    result = file_system->utimes(filename, times);
  } else {
    DANGERF("utimes: filename=%s times=%p", SAFE_CSTR(filename), times);
    // NB: Returning -1 breaks some NDK apps.
  }
  if (result == -1 && errno != ENOENT) {
    DANGERF("path=%s: %s",
            SAFE_CSTR(filename), safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_stat(const char* pathname, struct stat* buf) {
  ARC_STRACE_ENTER("stat", "\"%s\", %p", SAFE_CSTR(pathname), buf);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->stat(pathname, buf);
  else
    result = __real_stat(pathname, buf);
  if (result == -1 && errno != ENOENT)
    DANGERF("path=%s: %s", SAFE_CSTR(pathname), safe_strerror(errno).c_str());
  if (!result)
    ARC_STRACE_REPORT("buf=%s", arc::GetStatStr(buf).c_str());
  ARC_STRACE_RETURN(result);
}

int __wrap_close(int fd) {
  ARC_STRACE_ENTER_FD("close", "%d", fd);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->close(fd);
  else
    result = __real_close(fd);
  if (result == -1) {
    // Closing with a bad file descriptor may be indicating a double
    // close, which is more dangerous than it seems since everything
    // shares one address space and we reuse file descriptors quickly.
    // It can cause a newly allocated file descriptor in another
    // thread to now be unallocated.
    // We just use DANGERF() instead of LOG_FATAL_IF() because
    // cts.CtsNetTestCases:android.net.rtp.cts.AudioStreamTest#testDoubleRelease
    // hits the case.
    if (errno == EBADF)
      DANGERF("Close of bad file descriptor may indicate double close");
    DANGERF("fd=%d: %s", fd, safe_strerror(errno).c_str());
  }
  if (!result)
    ARC_STRACE_UNREGISTER_FD(fd);
  ARC_STRACE_RETURN(result);
}

int __wrap_creat(const char* pathname, mode_t mode) {
  ARC_STRACE_ENTER("creat", "\"%s\", 0%o", SAFE_CSTR(pathname), mode);
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    result = file_system->open(pathname, O_CREAT | O_WRONLY | O_TRUNC,
                                        mode);
  } else {
    errno = ENOSYS;
  }
  ARC_STRACE_REGISTER_FD(result, SAFE_CSTR(pathname));
  ARC_STRACE_RETURN(result);
}

int __wrap_dup(int oldfd) {
  ARC_STRACE_ENTER_FD("dup", "%d", oldfd);
  int fd = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    fd = file_system->dup(oldfd);
  } else {
    fd = __real_dup(oldfd);
  }
  if (fd == -1)
    DANGERF("oldfd=%d: %s", oldfd, safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(fd);
}

int __wrap_dup2(int oldfd, int newfd) {
  ARC_STRACE_ENTER_FD("dup2", "%d, %d", oldfd, newfd);
  int fd = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system) {
    fd = file_system->dup2(oldfd, newfd);
  } else {
    DANGERF("oldfd=%d newfd=%d", oldfd, newfd);
    errno = EBADF;
  }
  if (fd== -1) {
    DANGERF("oldfd=%d newfd=%d: %s",
            oldfd, newfd, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(fd);
}

// Although Linux has fcntl64 syscall, user code does not use it directly.
// Therefore, we do not have to wrap the 64bit variant.
int __wrap_fcntl(int fd, int cmd, ...) {
  // TODO(crbug.com/241955): Support variable args?
  ARC_STRACE_ENTER_FD("fcntl", "%d, %s, ...",
                        fd, arc::GetFcntlCommandStr(cmd).c_str());
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();

  if (file_system) {
    va_list ap;
    va_start(ap, cmd);
    result = file_system->fcntl(fd, cmd, ap);
    va_end(ap);
  } else {
    DANGER();
    errno = EINVAL;
  }

  if (result == -1)
    DANGERF("fd=%d cmd=%d: %s", fd, cmd, safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(result);
}

extern "C" int __wrap_fdatasync(int fd) {
  ARC_STRACE_ENTER_FD("fdatasync", "%d", fd);
  int result = 0;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->fdatasync(fd);
  ARC_STRACE_RETURN(result);
}

extern "C" int __wrap_fsync(int fd) {
  ARC_STRACE_ENTER_FD("fsync", "%d", fd);
  int result = 0;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->fsync(fd);
  ARC_STRACE_RETURN(result);
}

int __wrap_flock(int fd, int operation) {
  // We do not have to implement flock() and similar functions because:
  // - Each app has its own file system tree.
  // - Two instances of the same app do not run at the same time.
  // - App instance and Dexopt instance of an app do not access the file system
  //   at the same time.
  ARC_STRACE_ENTER_FD("flock", "%d, %s",
                        fd, arc::GetFlockOperationStr(operation).c_str());
  ARC_STRACE_REPORT("not implemented, always succeeds");
  ARC_STRACE_RETURN(0);
}

IRT_WRAPPER(fstat, int fd, struct nacl_abi_stat *buf) {
  ARC_STRACE_ENTER_FD("fstat", "%d, buf=%p", fd, buf);
  int result;
  struct stat st;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->fstat(fd, &st);
  else
    result = __real_fstat(fd, &st);
  if (result) {
    result = errno;
    DANGERF("fd=%d: %s", fd, safe_strerror(errno).c_str());
  } else {
    StatToNaClAbiStat(&st, buf);
    ARC_STRACE_REPORT("buf=%s", arc::GetNaClAbiStatStr(buf).c_str());
  }
  ARC_STRACE_RETURN_INT(result, result != 0);
}

template <typename OffsetType>
static int FtruncateImpl(int fd, OffsetType length) {
  ARC_STRACE_ENTER_FD("ftruncate", "%d, %lld",
                        fd, static_cast<int64_t>(length));
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->ftruncate(fd, length);
  else
    result = __real_ftruncate64(fd, length);
  if (result == -1) {
    DANGERF("fd=%d length=%lld: %s", fd, static_cast<int64_t>(length),
            safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_ftruncate(int fd, off_t length) {
  return FtruncateImpl(fd, length);
}

int __wrap_ftruncate64(int fd, off64_t length) {
  return FtruncateImpl(fd, length);
}

int __wrap_ioctl(int fd, int request, ...) {
  // TODO(crbug.com/241955): Support |request| constants and variable args?
  ARC_STRACE_ENTER_FD("ioctl", "%d, %d, ...", fd, request);
  int result = -1;
  va_list ap;
  va_start(ap, request);
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->ioctl(fd, request, ap);
  else
    errno = EINVAL;
  va_end(ap);
  if (result == -1)
    DANGERF("fd=%d request=%d: %s", fd, request, safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(result);
}

template <typename OffsetType>
static OffsetType LseekImpl(int fd, OffsetType offset, int whence) {
  ARC_STRACE_ENTER_FD("lseek", "%d, %lld, %s",
                        fd, static_cast<int64_t>(offset),
                        arc::GetLseekWhenceStr(whence).c_str());
  OffsetType result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->lseek(fd, offset, whence);
  else
    result = __real_lseek64(fd, offset, whence);
  if (result == -1) {
    DANGERF("fd=%d offset=%lld whence=%d: %s",
            fd, static_cast<int64_t>(offset), whence,
            safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

off64_t __wrap_lseek64(int fd, off64_t offset, int whence) {
  return LseekImpl(fd, offset, whence);
}

// NB: Do NOT use off64_t for |offset|. It is not compatible with Bionic.
// Bionic's mmap() does not support large file, and it does not provide
// mmap64() either.
void* __wrap_mmap(
    void* addr, size_t length, int prot, int flags, int fd, off_t offset) {
  // ARC_STRACE_ENTER_FD expects FD is the first argument.
  ARC_STRACE_ENTER_FD(
      "mmap", "%d, addr=%p, length=%zu(0x%zx), %s, %s, offset=0x%llx",
      fd, addr, length, length,
      arc::GetMmapProtStr(prot).c_str(),
      arc::GetMmapFlagStr(flags).c_str(),
      static_cast<int64_t>(offset));
  // WRITE + EXEC mmap is not allowed.
  if ((prot & PROT_WRITE) && (prot & PROT_EXEC)) {
    ALOGE("mmap with PROT_WRITE + PROT_EXEC! "
          "addr=%p length=%zu prot=%d flags=%d fd=%d offset=%lld",
          addr, length, prot, flags, fd, static_cast<int64_t>(offset));
    // However, with Bare Metal, our JIT engines or NDK apps may want WX mmap.
#if defined(__native_client__)
    ALOG_ASSERT(false, "PROT_WRITE + PROT_EXEC mmap is not allowed");
    // This mmap call gracefully fails in release build.
#endif
  } else if (prot & PROT_EXEC) {
    // There are two reasons we will see PROT_EXEC:
    // - The Bionic loader use PROT_EXEC to map dlopen-ed files. Note
    //   that we inject posix_translation based file operations to the
    //   Bionic loader. See src/common/dlfcn_injection.cc for detail.
    // - On Bare Metal ARM, v8 uses PROT_EXEC to run JIT-ed code directly.
    //
    // But it is still an interesting event. So, we log this by ALOGI.
    ALOGI("mmap with PROT_EXEC! "
          "addr=%p length=%zu prot=%d flags=%d fd=%d offset=%lld",
          addr, length, prot, flags, fd, static_cast<int64_t>(offset));
  }

  void* result = MAP_FAILED;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->mmap(addr, length, prot, flags, fd, offset);
  else
    result = __real_mmap(addr, length, prot, flags, fd, offset);
#if defined(USE_VERBOSE_MEMORY_VIEWER)
  if (result != MAP_FAILED)
    arc::MemoryMappingBacktraceMap::GetInstance()->
        MapCurrentStackFrame(result, length);
#endif

  // Overwrite |errno| to emulate Bionic's behavior. See the comment in
  // mods/android/bionic/libc/unistd/mmap.c.
  if (result && (flags & (MAP_PRIVATE | MAP_ANONYMOUS))) {
    if ((result != MAP_FAILED) &&
        (flags & MAP_PRIVATE) && (flags & MAP_ANONYMOUS)) {
      // In this case, madvise(MADV_MERGEABLE) in mmap.c will likely succeed.
      // Do not update |errno|.
    } else {
      // Overwrite |errno| with EINVAL even when |result| points to a valid
      // address.
      errno = EINVAL;
    }
  }

  if (result == MAP_FAILED) {
    DANGERF("addr=%p length=%zu prot=%d flags=%d fd=%d offset=%lld: %s",
            addr, length, prot, flags, fd, static_cast<int64_t>(offset),
            safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN_PTR(result, result == MAP_FAILED);
}

int __wrap_mprotect(const void* addr, size_t len, int prot) {
  ARC_STRACE_ENTER("mprotect", "%p, %zu(0x%zx), %s", addr, len, len,
                     arc::GetMmapProtStr(prot).c_str());
#if defined(__native_client__)
  // PROT_EXEC mprotect is not allowed on NaCl, where all executable
  // pages are validated through special APIs.
  if (prot & PROT_EXEC) {
    ALOGE("mprotect with PROT_EXEC! addr=%p length=%zu prot=%d",
          addr, len, prot);
    ALOG_ASSERT(false, "mprotect with PROT_EXEC is not allowed");
    // This mmap call gracefully fails in release build.
  }
#else
  if ((prot & PROT_WRITE) && (prot & PROT_EXEC)) {
    // TODO(crbug.com/365349): Currently, it seems Dalvik JIT is
    // enabled on Bare Metal ARM. Disable it and increase the
    // verbosity of this ALOG.
    ALOGV("mprotect with PROT_WRITE + PROT_EXEC! addr=%p length=%zu prot=%d",
          addr, len, prot);
  }
#endif

  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  const int errno_orig = errno;
  if (file_system)
    result = file_system->mprotect(addr, len, prot);
  if (!file_system || (result != 0 && errno == ENOSYS)) {
    // TODO(crbug.com/362862): Stop falling back to __real on ENOSYS and
    // do this only for unit tests.
    ARC_STRACE_REPORT("falling back to __real");
    result = __real_mprotect(addr, len, prot);
    if (!result && errno == ENOSYS)
      errno = errno_orig;  // restore |errno| overwritten by posix_translation
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_munmap(void* addr, size_t length) {
  ARC_STRACE_ENTER("munmap", "%p, %zu(0x%zx)", addr, length, length);
  ARC_STRACE_REPORT("RANGE (%p-%p)",
                      addr, reinterpret_cast<char*>(addr) + length);
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  const int errno_orig = errno;
  if (file_system)
    result = file_system->munmap(addr, length);
  if (!file_system || (result != 0 && errno == ENOSYS)) {
    // TODO(crbug.com/362862): Stop falling back to __real on ENOSYS and
    // do this only for unit tests.
    ARC_STRACE_REPORT("falling back to __real");
    result = __real_munmap(addr, length);
    if (!result && errno == ENOSYS)
      errno = errno_orig;  // restore |errno| overwritten by posix_translation
  }
#if defined(USE_VERBOSE_MEMORY_VIEWER)
  if (result == 0)
    arc::MemoryMappingBacktraceMap::GetInstance()->Unmap(addr, length);
#endif
  ARC_STRACE_RETURN(result);
}

int __wrap_poll(struct pollfd* fds, nfds_t nfds, int timeout) {
  // TODO(crbug.com/241955): Stringify |fds|?
  ARC_STRACE_ENTER("poll", "%p, %lld, %d",
                     fds, static_cast<int64_t>(nfds), timeout);
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->poll(fds, nfds, timeout);
  else
    result = __real_poll(fds, nfds, timeout);
  if (result == -1) {
    DANGERF("fds=%p nfds=%u timeout=%d[ms]: %s",
            fds, nfds, timeout, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

template <typename OffsetType>
static ssize_t PreadImpl(int fd, void* buf, size_t count, OffsetType offset) {
  ARC_STRACE_ENTER_FD("pread", "%d, %p, %zu, %lld",
                        fd, buf, count, static_cast<int64_t>(offset));
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->pread(fd, buf, count, offset);
  else
    result = __real_pread64(fd, buf, count, offset);
  if (result == -1) {
    DANGERF("fd=%d buf=%p count=%zu offset=%lld: %s",
            fd, buf, count, static_cast<int64_t>(offset),
            safe_strerror(errno).c_str());
  }
  if (result >= 0)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_pread(int fd, void* buf, size_t count, off_t offset) {
  return PreadImpl(fd, buf, count, offset);
}

ssize_t __wrap_pread64(int fd, void* buf, size_t count, off64_t offset) {
  return PreadImpl(fd, buf, count, offset);
}

template <typename OffsetType>
static ssize_t PwriteImpl(int fd, const void* buf, size_t count,
                          OffsetType offset) {
  ARC_STRACE_ENTER_FD("pwrite", "%d, %p, %zu, %lld",
                        fd, buf, count, static_cast<int64_t>(offset));
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->pwrite(fd, buf, count, offset);
  else
    result = __real_pwrite64(fd, buf, count, offset);
  if (result == -1) {
    DANGERF("fd=%d buf=%p count=%zu offset=%lld: %s",
            fd, buf, count, static_cast<int64_t>(offset),
            safe_strerror(errno).c_str());
  }
  if (errno != EFAULT)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, count).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_pwrite(int fd, const void* buf, size_t count, off_t offset) {
  return PwriteImpl(fd, buf, count, offset);
}

ssize_t __wrap_pwrite64(int fd, const void* buf, size_t count,
                        off64_t offset) {
  return PwriteImpl(fd, buf, count, offset);
}

ssize_t __wrap_read(int fd, void* buf, size_t count) {
  ARC_STRACE_ENTER_FD("read", "%d, %p, %zu", fd, buf, count);
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->read(fd, buf, count);
  else
    result = __real_read(fd, buf, count);
  if (result == -1 && errno != EAGAIN) {
    DANGERF("fd=%d buf=%p count=%zu: %s",
            fd, buf, count, safe_strerror(errno).c_str());
  }
  if (result >= 0)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_readv(int fd, const struct iovec* iov, int iovcnt) {
  // TODO(crbug.com/241955): Stringify |iov|?
  ARC_STRACE_ENTER_FD("readv", "%d, %p, %d", fd, iov, iovcnt);
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->readv(fd, iov, iovcnt);
  else
    result = __real_readv(fd, iov, iovcnt);
  if (result == -1) {
    DANGERF("fd=%d iov=%p iovcnt=%d: %s",
            fd, iov, iovcnt, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_rmdir(const char* pathname) {
  ARC_STRACE_ENTER("rmdir", "\"%s\"", SAFE_CSTR(pathname));
  int result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->rmdir(pathname);
  else
    result = __real_rmdir(pathname);
  if (result == -1 && errno != ENOENT)
    DANGERF("path=%s: %s", SAFE_CSTR(pathname), safe_strerror(errno).c_str());
  ARC_STRACE_RETURN(result);
}

int __wrap_utime(const char* filename, const struct utimbuf* times) {
  ARC_STRACE_ENTER("utime", "\"%s\", %p", SAFE_CSTR(filename), times);
  int result = -1;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->utime(filename, times);
  else
    errno = ENOSYS;
  if (result == -1 && errno != ENOENT) {
    DANGERF("path=%s: %s",
            SAFE_CSTR(filename), safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_write(int fd, const void* buf, size_t count) {
  const int wrap_write_nest_count = g_wrap_write_nest_count.Get();
  if (wrap_write_nest_count) {
    // Calling write() to a stdio descriptor inside __wrap_write may cause
    // infinite wrap loop. Here, we show a warning, and just return.
    // It may happen when a chromium base DCHECK fails, e.g. inside AutoLock.
    ALOGE("write() for stdio is called inside __wrap_write(): "
          "fd=%d count=%zu buf=%p msg='%s'",
          fd, count, buf,
          std::string(static_cast<const char*>(buf), count).c_str());
    return 0;
  } else {
    ARC_STRACE_ENTER_FD("write", "%d, %p, %zu", fd, buf, count);
    g_wrap_write_nest_count.Set(wrap_write_nest_count + 1);
    int result;
    VirtualFileSystemInterface* file_system = GetFileSystem();
    if (file_system)
      result = file_system->write(fd, buf, count);
    else
      result = __real_write(fd, buf, count);
    if (errno != EFAULT)
      ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, count).c_str());
    g_wrap_write_nest_count.Set(wrap_write_nest_count);
    if (result == -1) {
      DANGERF("fd=%d buf=%p count=%zu: %s",
              fd, buf, count, safe_strerror(errno).c_str());
    }
    ARC_STRACE_RETURN(result);
  }
}

ssize_t __wrap_writev(int fd, const struct iovec* iov, int iovcnt) {
  // TODO(crbug.com/241955): Output the first N bytes in |iov|.
  // TODO(crbug.com/241955): Stringify |iov|?
  ARC_STRACE_ENTER_FD("writev", "%d, %p, %d", fd, iov, iovcnt);
  ssize_t result;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    result = file_system->writev(fd, iov, iovcnt);
  else
    result = __real_writev(fd, iov, iovcnt);
  if (result == -1) {
    DANGERF("fd=%d iov=%p iovcnt=%d: %s",
            fd, iov, iovcnt, safe_strerror(errno).c_str());
  }
  ARC_STRACE_RETURN(result);
}

mode_t __wrap_umask(mode_t mask) {
  ARC_STRACE_ENTER("umask", "0%o", mask);
  mode_t return_umask;
  VirtualFileSystemInterface* file_system = GetFileSystem();
  if (file_system)
    return_umask = file_system->umask(mask);
  else
    return_umask = __real_umask(mask);
  ARC_STRACE_RETURN(return_umask);
}

extern "C" {
// The following is an example call stach when close() is called:
//
// our_function_that_calls_close()
//   close()  // in Bionic
//     __nacl_irt_close()  // function pointer call
//        __nacl_irt_close_wrap()  // this function
//          __wrap_close()  // in file_wrap.cc
//             FileSystem::close()  // in posix_translation
//
// Also note that code in posix_translation/ is always able to call into the
// original IRT by calling __real_close() defined in file_wrap.cc.
IRT_WRAPPER(close, int fd) {
  int result = __wrap_close(fd);
  return !result ? 0 : errno;
}

// See native_client/src/trusted/service_runtime/include/sys/fcntl.h
#define NACL_ABI_O_SYNC 010000

IRT_WRAPPER(open, const char *pathname, int oflag, mode_t cmode, int *newfd) {
  // |oflag| is mostly compatible between NaCl and Bionic, O_SYNC is
  // the only exception.
  int bionic_oflag = oflag;
  if ((bionic_oflag & NACL_ABI_O_SYNC)) {
    bionic_oflag &= ~NACL_ABI_O_SYNC;
    bionic_oflag |= O_SYNC;
  }
  *newfd = __wrap_open(pathname, oflag, cmode);
  return *newfd >= 0 ? 0 : errno;
}

IRT_WRAPPER(read, int fd, void *buf, size_t count, size_t *nread) {
  ssize_t result = __wrap_read(fd, buf, count);
  *nread = result;
  return result >= 0 ? 0 : errno;
}

IRT_WRAPPER(seek, int fd, off64_t offset, int whence, off64_t *new_offset) {
  *new_offset = __wrap_lseek64(fd, offset, whence);
  return *new_offset >= 0 ? 0 : errno;
}

IRT_WRAPPER(write, int fd, const void *buf, size_t count, size_t *nwrote) {
  ssize_t result = __wrap_write(fd, buf, count);
  *nwrote = result;
  return result >= 0 ? 0 : errno;
}

// We implement IRT wrappers using __wrap_* functions. As the wrap
// functions or posix_translation/ may call __real_* functions, we
// define them using real IRT interfaces.

int __real_close(int fd) {
  ALOG_ASSERT(__nacl_irt_close_real);
  int result = __nacl_irt_close_real(fd);
  if (result) {
    errno = result;
    return -1;
  }
  return 0;
}

int __real_fstat(int fd, struct stat *buf) {
  ALOG_ASSERT(__nacl_irt_fstat_real);
  struct nacl_abi_stat nacl_buf;
  int result = __nacl_irt_fstat_real(fd, &nacl_buf);
  if (result) {
    errno = result;
    return -1;
  }
  NaClAbiStatToStat(&nacl_buf, buf);
  return 0;
}

char* __real_getcwd(char *buf, size_t size) {
  ALOG_ASSERT(__nacl_irt_getcwd_real);
  // Note: If needed, you can implement it with __nacl_irt_getcwd_real in the
  // same way as android/bionic/libc/bionic/getcwd.cpp. __nacl_irt_getcwd_real
  // and __getcwd (in Bionic) has the same interface.
  ALOG_ASSERT(false, "not implemented");
  return NULL;
}

int __real_open(const char *pathname, int oflag, mode_t cmode) {
  ALOG_ASSERT(__nacl_irt_open_real);
  int newfd;
  // |oflag| is mostly compatible between NaCl and Bionic, O_SYNC is
  // the only exception.
  int nacl_oflag = oflag;
  if ((nacl_oflag & O_SYNC)) {
    nacl_oflag &= ~O_SYNC;
    nacl_oflag |= NACL_ABI_O_SYNC;
  }
  int result = __nacl_irt_open_real(pathname, oflag, cmode, &newfd);
  if (result) {
    errno = result;
    return -1;
  }
  return newfd;
}

ssize_t __real_read(int fd, void *buf, size_t count) {
  ALOG_ASSERT(__nacl_irt_read_real);
  size_t nread;
  int result = __nacl_irt_read_real(fd, buf, count, &nread);
  if (result) {
    errno = result;
    return -1;
  }
  return nread;
}

off64_t __real_lseek64(int fd, off64_t offset, int whence) {
  ALOG_ASSERT(__nacl_irt_seek_real);
  off64_t nacl_offset;
  int result = __nacl_irt_seek_real(fd, offset, whence, &nacl_offset);
  if (result) {
    errno = result;
    return -1;
  }
  return nacl_offset;
}

ssize_t __real_write(int fd, const void *buf, size_t count) {
  ALOG_ASSERT(__nacl_irt_write_real);
  size_t nwrote;
  int result = __nacl_irt_write_real(fd, buf, count, &nwrote);
  if (result) {
    errno = result;
    return -1;
  }
  return nwrote;
}
}  // extern "C"

namespace {

void direct_stderr_write(const void* buf, size_t count) {
  ALOG_ASSERT(__nacl_irt_write_real);
  size_t nwrote;
  __nacl_irt_write_real(STDERR_FILENO, buf, count, &nwrote);
}

}  // namespace

namespace arc {

// The call stack gets complicated when IRT is hooked. See the comment near
// IRT_WRAPPER(close) for more details.
#if defined(LIBWRAP_FOR_TEST)
__attribute__((constructor))
#endif
void InitIRTHooks() {
  DO_WRAP(close);
  DO_WRAP(fstat);
  DO_WRAP(getcwd);
  DO_WRAP(open);
  DO_WRAP(read);
  DO_WRAP(seek);
  DO_WRAP(write);

  // We have replaced __nacl_irt_* above. Then, we need to inject them
  // to the Bionic loader.
  InitDlfcnInjection();

  SetLogWriter(direct_stderr_write);
}

// This table is exported to higher levels to define how they should dispatch
// through to libc.
const LibcDispatchTable g_libc_dispatch_table = {
  __real_close,
  __real_fdatasync,  // no IRT hook
  __real_fstat,
  __real_fsync,  // no IRT hook
  __real_lseek64,
  __real_mmap,  //  no IRT hook
  __real_mprotect,
  __real_munmap,  //  no IRT hook
  __real_open,
  __real_read,
  __real_write,
};

}  // namespace arc
