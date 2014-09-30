// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/inotify.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/signalfd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/vfs.h>
#include <unistd.h>

#include "base/basictypes.h"
#include "common/arc_strace.h"
#include "common/danger.h"
#include "common/file_util.h"
#include "wrap/file_wrap_private.h"

// Following stub functions are file related functions which are not
// called so far. We make sure they are not called by assertion.

extern "C" int __wrap_fchdir(int fd) {
  ARC_STRACE_ENTER_FD("fchdir", "%d", fd);
  // TODO(crbug.com/178515): Implement this.
  DANGERF("fchdir: fd=%d", fd);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_fstatfs(int fd, struct statfs* buf) {
  ARC_STRACE_ENTER_FD("fstatfs", "%d, %p", fd, buf);
  DANGERF("fstatfs: fd=%d buf=%p", fd, buf);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_lchown(const char* path, uid_t owner, gid_t group) {
  ARC_STRACE_ENTER("lchown", "\"%s\", %u, %u",
                     SAFE_CSTR(path), owner, group);
  DANGERF("lchown: path=%s owner=%u group=%u",
          SAFE_CSTR(path), owner, group);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_mlock(const void* addr, size_t len) {
  ARC_STRACE_ENTER("mlock", "%p, %zu", addr, len);
  DANGERF("mlock: addr=%p len=%zu", addr, len);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_mlockall(int flags) {
  // TODO(crbug.com/241955): Stringify |flags|?
  ARC_STRACE_ENTER("mlockall", "%d", flags);
  DANGERF("mlockall: flags=%d", flags);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_mount(const char* source, const char* target,
                            const char* filesystemtype,
                            unsigned long mountflags,   // NOLINT(runtime/int)
                            const void* data) {
  // TODO(crbug.com/241955): Stringify |mountflags|?
  ARC_STRACE_ENTER("mount", "\"%s\", \"%s\", \"%s\", %lu, %p",
                     SAFE_CSTR(source), SAFE_CSTR(target),
                     SAFE_CSTR(filesystemtype), mountflags, data);
  DANGERF("mount: source=%s target=%s "
          "filesystemtype=%s mountflags=%lu data=%p",
          SAFE_CSTR(source), SAFE_CSTR(target),
          SAFE_CSTR(filesystemtype), mountflags, data);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" void* __wrap_mremap(void* old_address, size_t old_size,
                               size_t new_size, int flags,  ...) {
  ARC_STRACE_ENTER("mremap", "%p, %zu, %zu, %s",
                     old_address, old_size, new_size,
                     arc::GetMremapFlagStr(flags).c_str());
  DANGERF("mremap: old_address=%p old_size=%zu new_size=%zu flags=%d",
          old_address, old_size, new_size, flags);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN_PTR(MAP_FAILED, true);
}

extern "C" int __wrap_munlock(const void* addr, size_t len) {
  ARC_STRACE_ENTER("munlock", "%p, %zu", addr, len);
  DANGERF("munlock: addr=%p len=%zu", addr, len);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_munlockall() {
  ARC_STRACE_ENTER("munlockall", "%s", "");
  DANGERF("munlockall");
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_umount(const char* target) {
  ARC_STRACE_ENTER("umount", "\"%s\"", SAFE_CSTR(target));
  DANGERF("umount: target=%s", SAFE_CSTR(target));
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_umount2(const char* target, int flags) {
  // TODO(crbug.com/241955): Stringify |flags|?
  ARC_STRACE_ENTER("umount2", "\"%s\", %d", SAFE_CSTR(target), flags);
  DANGERF("umount2: target=%s flags=%d", SAFE_CSTR(target), flags);
  ALOG_ASSERT(0);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

// The following stub functions are being called so we are just
// calling the real implementation or returning zero. For each function,
// we need to either 1. remove it if NaCl's libc has the implementation,
// or 2. implement it by ourselves.
extern "C" int __wrap_chmod(const char* path, mode_t mode) {
  // TODO(crbug.com/242355): Implement this.
  ARC_STRACE_ENTER("chmod", "\"%s\", 0%o", SAFE_CSTR(path), mode);
  ARC_STRACE_REPORT("not implemented yet");
  ARC_STRACE_RETURN(0);  // Returning -1 breaks SQLite.
}

extern "C" int __wrap_eventfd(unsigned int initval, int flags) {
  ARC_STRACE_ENTER("eventfd", "%u, %d", initval, flags);
  ARC_STRACE_REPORT("not implemented yet");
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_fchmod(int fd, mode_t mode) {
  // TODO(crbug.com/242355): Implement this.
  ARC_STRACE_ENTER_FD("fchmod", "%d, 0%o", fd, mode);
  ARC_STRACE_REPORT("not implemented yet");
  ARC_STRACE_RETURN(0);
}

extern "C" int __wrap_fchown(int fd, uid_t owner, gid_t group) {
  // TODO(crbug.com/242355): Implement this.
  ARC_STRACE_ENTER_FD("fchown", "%d, %u, %u", fd, owner, group);
  ARC_STRACE_REPORT("not implemented yet");
  ARC_STRACE_RETURN(0);
}

extern "C" int __wrap_futimens(int fd, const struct timespec times[2]) {
  ARC_STRACE_ENTER_FD("futimens", "%d, %p", fd, times);
  ARC_STRACE_REPORT("not implemented yet");
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_inotify_add_watch(int fd, const char* pathname,
                                        uint32_t mask) {
  ARC_STRACE_ENTER_FD("inotify_add_watch", "%d, \"%s\", %u",
                        fd, SAFE_CSTR(pathname), mask);
  // TODO(crbug.com/236903): Implement this.
  DANGERF("inotify_add_watch: fd=%d pathname=%s mask=%u",
          fd, SAFE_CSTR(pathname), mask);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_inotify_init() {
  ARC_STRACE_ENTER("inotify_init", "%s", "");
  // TODO(crbug.com/236903): Implement this.
  DANGERF("inotify_init");
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_inotify_rm_watch(int fd, int wd) {
  ARC_STRACE_ENTER_FD("inotify_rm_watch", "%d, %d", fd, wd);
  // TODO(crbug.com/236903): Implement this.
  DANGERF("inotify_rm_watch: fd=%d wd=%d", fd, wd);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

extern "C" int __wrap_msync(void* addr, size_t length, int flags) {
  ARC_STRACE_ENTER("msync", "%p, %zu, %d", addr, length, flags);
  ARC_STRACE_REPORT("not implemented yet");
  // msync is called by dexopt and some apps (crbug.com/363545). Although dexopt
  // does not check the return value, the apps may. Return 0 without doing
  // anything so that such apps will not fail. This should be safe as long as
  // the app passes the mixed mmap/read/write checks in pepper_file.cc.
  // TODO(crbug.com/242753): We might have to implement this through NaCl and
  // Bare Metal IRT when we migrate to the real multi-process model.
  ARC_STRACE_RETURN(0);
}
