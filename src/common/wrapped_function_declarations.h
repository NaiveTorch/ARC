// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Forward declarations necessary to define the table of wrapped
// functions.
//

#ifndef COMMON_WRAPPED_FUNCTION_DECLARATIONS_H_
#define COMMON_WRAPPED_FUNCTION_DECLARATIONS_H_

#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <grp.h>
#include <netdb.h>
#include <poll.h>
#include <pthread.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/file.h>
#include <sys/inotify.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/resource.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/timerfd.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/utsname.h>
#include <sys/vfs.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utime.h>

extern "C" {
// Bionic does not have forward declarations for them.
int getdents(unsigned int fd, struct dirent* dirp, unsigned int count);
int mkstemps(char* path, int slen);
int tgkill(int tgid, int tid, int sig);
int tkill(int tid, int sig);
int truncate64(const char* path, off_t length);

// TODO(crbug.com/350701): Remove them once we have removed glibc
// support and had some kind of check for symbols in Bionic.
int epoll_create1(int flags);
int epoll_pwait(int epfd, struct epoll_event* events,
                int maxevents, int timeout,
                const sigset_t* sigmask);
int inotify_init1(int flags);
int mkostemp(char* tmpl, int flags);
int mkostemps(char* tmpl, int suffixlen, int flags);
int ppoll(struct pollfd* fds, nfds_t nfds,
          const struct timespec* timeout_ts, const sigset_t* sigmask);
ssize_t preadv(int fd, const struct iovec* iov, int iovcnt,
               off_t offset);
ssize_t pwritev(int fd, const struct iovec* iov, int iovcnt,
                off_t offset);
}

#endif  // COMMON_WRAPPED_FUNCTION_DECLARATIONS_H_
