// ARC MOD TRACK "third_party/android/bionic/libc/bionic/dirent.cpp"
/*
 * Copyright (C) 2008 The Android Open Source Project
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *  * Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *  * Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */

#include <dirent.h>

#include <errno.h>
#include <fcntl.h>
// ARC MOD BEGIN UPSTREAM bionic-add-missing-include
#include <stdlib.h>
// ARC MOD END UPSTREAM
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

// ARC MOD BEGIN
// private/ScopedPthreadMutexLocker.h is moved to common.
#include "common/scoped_pthread_mutex_locker.h"
#include "common/arc_strace.h"

// The following is an inline include of
// "third_party/android/bionic/libc/private/ErrnoRestorer.h".
// This file is used in src/wrap and we inline include ErrnoRestorer
// to prevent the need to include headers deep inside Android source.
#ifndef ERRNO_RESTORER_H
#define ERRNO_RESTORER_H

class ErrnoRestorer {
 public:
  explicit ErrnoRestorer() : saved_errno_(errno) {
  }

  ~ErrnoRestorer() {
    errno = saved_errno_;
  }

  void override(int new_errno) {
    saved_errno_ = new_errno;
  }

 private:
  int saved_errno_;

  // Disallow copy and assignment.
  ErrnoRestorer(const ErrnoRestorer&);
  void operator=(const ErrnoRestorer&);
};

#endif // ERRNO_RESTORER_H

// This file exists in order to provide the opendir-style functions
// in terms of system calls in libwrap so we can implement the directory
// reading system calls directly in posix_translation.  libwrap is subject to
// wrapping rules, so these system calls will go into file_wrap.cc wrappers.

// Make all these functions wrap functions.
#define alphasort __wrap_alphasort
#define closedir __wrap_closedir
#define dirfd __wrap_dirfd
#define fdopendir __wrap_fdopendir
#define opendir __wrap_opendir
#define rewinddir __wrap_rewinddir
#define readdir __wrap_readdir
#define readdir_r __wrap_readdir_r
// ARC MOD END

struct DIR {
  int fd_;
  size_t available_bytes_;
  dirent* next_;
  pthread_mutex_t mutex_;
  dirent buff_[15];
};
// ARC MOD BEGIN
extern "C" {
// ARC MOD END

static DIR* __allocate_DIR(int fd) {
  DIR* d = reinterpret_cast<DIR*>(malloc(sizeof(DIR)));
  if (d == NULL) {
    return NULL;
  }
  d->fd_ = fd;
  d->available_bytes_ = 0;
  d->next_ = NULL;
  pthread_mutex_init(&d->mutex_, NULL);
  return d;
}

int dirfd(DIR* dirp) {
  // ARC MOD BEGIN
  ARC_STRACE_ENTER("dirfd", "%p", dirp);
  const int result = dirp->fd_;
  ARC_STRACE_RETURN(result);
  // ARC MOD END
}

DIR* fdopendir(int fd) {
  // ARC MOD BEGIN
  ARC_STRACE_ENTER_FD("fdopendir", "%d", fd);
  // ARC MOD END
  // Is 'fd' actually a directory?
  struct stat sb;
  if (fstat(fd, &sb) == -1) {
    // ARC MOD BEGIN
    ARC_STRACE_RETURN_PTR(NULL, true);
    // ARC MOD END
  }
  if (!S_ISDIR(sb.st_mode)) {
    errno = ENOTDIR;
    // ARC MOD BEGIN
    ARC_STRACE_RETURN_PTR(NULL, true);
    // ARC MOD END
  }

  // ARC MOD BEGIN
  DIR* result = __allocate_DIR(fd);
  ARC_STRACE_RETURN_PTR(result, !result);
  // ARC MOD END
}

DIR* opendir(const char* path) {
  // ARC MOD BEGIN
  ARC_STRACE_ENTER("opendir", "\"%s\"", SAFE_CSTR(path));
  // ARC MOD END
  int fd = open(path, O_RDONLY | O_DIRECTORY);
  // ARC MOD BEGIN
  DIR* result = (fd != -1) ? __allocate_DIR(fd) : NULL;
  ARC_STRACE_RETURN_PTR(result, !result);
  // ARC MOD END
}

static bool __fill_DIR(DIR* d) {
  int rc = TEMP_FAILURE_RETRY(getdents(d->fd_, d->buff_, sizeof(d->buff_)));
  if (rc <= 0) {
    return false;
  }
  d->available_bytes_ = rc;
  d->next_ = d->buff_;
  return true;
}

static dirent* __readdir_locked(DIR* d) {
  if (d->available_bytes_ == 0 && !__fill_DIR(d)) {
    return NULL;
  }

  dirent* entry = d->next_;
  d->next_ = reinterpret_cast<dirent*>(reinterpret_cast<char*>(entry) + entry->d_reclen);
  d->available_bytes_ -= entry->d_reclen;
  return entry;
}

dirent* readdir(DIR* d) {
  // ARC MOD BEGIN
  // Use ENTER_FD with |d->fd_| for better annotation.
  ARC_STRACE_ENTER_FD("readdir", "%d, %p", d ? d->fd_ : -1, d);
  // ARC MOD END
  ScopedPthreadMutexLocker locker(&d->mutex_);
  // ARC MOD BEGIN
  dirent* result = __readdir_locked(d);
  ARC_STRACE_RETURN_PTR(result, !result);
  // ARC MOD END
}

int readdir_r(DIR* d, dirent* entry, dirent** result) {
  // ARC MOD BEGIN
  // Use ENTER_FD with |d->fd_| for better annotation.
  ARC_STRACE_ENTER_FD("readdir_r", "%d, %p, %p, %p",
                        d ? d->fd_ : -1, d, entry, result);
  // ARC MOD END
  ErrnoRestorer errno_restorer;

  *result = NULL;
  errno = 0;

  ScopedPthreadMutexLocker locker(&d->mutex_);

  dirent* next = __readdir_locked(d);
  if (errno != 0 && next == NULL) {
    // ARC MOD BEGIN
    ARC_STRACE_RETURN_INT(errno, true);
    // ARC MOD END
  }

  if (next != NULL) {
    memcpy(entry, next, next->d_reclen);
    *result = entry;
  }
  // ARC MOD BEGIN
  ARC_STRACE_RETURN(0);
  // ARC MOD END
}

int closedir(DIR* d) {
  // ARC MOD BEGIN
  // Use ENTER_FD with |d->fd_| for better annotation.
  ARC_STRACE_ENTER_FD("closedir", "%d, %p", d ? d->fd_ : -1, d);
  // ARC MOD END
  if (d == NULL) {
    errno = EINVAL;
    // ARC MOD BEGIN
    ARC_STRACE_RETURN(-1);
    // ARC MOD END
  }

  int fd = d->fd_;
  pthread_mutex_destroy(&d->mutex_);
  free(d);
  // ARC MOD BEGIN
  const int result = close(fd);
  ARC_STRACE_RETURN(result);
  // ARC MOD END
}

void rewinddir(DIR* d) {
  // ARC MOD BEGIN
  // Use ENTER_FD with |d->fd_| for better annotation.
  ARC_STRACE_ENTER_FD("rewinddir", "%d, %p", d ? d->fd_ : -1, d);
  // ARC MOD END
  ScopedPthreadMutexLocker locker(&d->mutex_);
  lseek(d->fd_, 0, SEEK_SET);
  d->available_bytes_ = 0;
  // ARC MOD BEGIN
  ARC_STRACE_RETURN_VOID();
  // ARC MOD END
}

int alphasort(const dirent** a, const dirent** b) {
  return strcoll((*a)->d_name, (*b)->d_name);
}
// ARC MOD BEGIN
}
// ARC MOD END
