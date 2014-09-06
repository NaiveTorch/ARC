// Copyright (C) 2014 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// This file defines system calls NaCl does not support but nacl-glibc
// does have implementations which return -1 with ENOSYS.
//
// This file should be used only for syscalls which are not defined in
// third_party/nacl-glibc/sysdeps/nacl. Such system calls are defined
// in GPL code so you cannot use ARC MOD TRACK for them.
//

#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/capability.h>
#include <sys/epoll.h>
#include <sys/file.h>
#include <sys/inotify.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/select.h>
#include <sys/sendfile.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/sysinfo.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/utsname.h>
#include <unistd.h>
#include <utime.h>

#include <irt_syscalls.h>

#define DEFINE_ENOSYS_SYSCALL(ret, name, ...)   \
  ret name(__VA_ARGS__) {                       \
    errno = ENOSYS;                             \
    return -1;                                  \
  }

DEFINE_ENOSYS_SYSCALL(void *, __brk, void *addr)
DEFINE_ENOSYS_SYSCALL(int, __fcntl64, int fd, int cmd, ...)
DEFINE_ENOSYS_SYSCALL(pid_t, __fork, void)
DEFINE_ENOSYS_SYSCALL(int, __ioctl, int d, int request, ...)
DEFINE_ENOSYS_SYSCALL(long, __ptrace, int request, pid_t pid,
                      void *addr, void *data)
DEFINE_ENOSYS_SYSCALL(int, __sigsuspend, const sigset_t *mask)
DEFINE_ENOSYS_SYSCALL(int, accept, int sockfd, struct sockaddr *addr,
                      socklen_t *addrlen)
DEFINE_ENOSYS_SYSCALL(int, access, const char *pathname, int mode)
DEFINE_ENOSYS_SYSCALL(int, acct, const char *filename)
DEFINE_ENOSYS_SYSCALL(int, bind, int sockfd, const struct sockaddr *addr,
                      socklen_t addrlen)
DEFINE_ENOSYS_SYSCALL(int, capget,
                      cap_user_header_t hdrp, cap_user_data_t datap)
DEFINE_ENOSYS_SYSCALL(int, capset, cap_user_header_t hdrp,
                      const cap_user_data_t datap);
DEFINE_ENOSYS_SYSCALL(int, chdir, const char *path)
DEFINE_ENOSYS_SYSCALL(int, chmod, const char *path, mode_t mode)
DEFINE_ENOSYS_SYSCALL(int, chown, const char *path, uid_t owner, gid_t group)
DEFINE_ENOSYS_SYSCALL(int, chroot, const char* path)
DEFINE_ENOSYS_SYSCALL(int, clock_settime,
                      clockid_t clk_id, const struct timespec *tp)
DEFINE_ENOSYS_SYSCALL(int, connect, int sockfd, const struct sockaddr *addr,
                      socklen_t addrlen)
DEFINE_ENOSYS_SYSCALL(int, delete_module, const char *name, int flags)
DEFINE_ENOSYS_SYSCALL(int, epoll_create, int size)
DEFINE_ENOSYS_SYSCALL(int, epoll_ctl, int epfd, int op, int fd,
                      struct epoll_event *event)
DEFINE_ENOSYS_SYSCALL(int, epoll_wait, int epfd, struct epoll_event *events,
                      int maxevents, int timeout)
DEFINE_ENOSYS_SYSCALL(int, eventfd, unsigned int initval, int flags)
DEFINE_ENOSYS_SYSCALL(int, execve, const char *filename, char *const argv[],
                      char *const envp[])
DEFINE_ENOSYS_SYSCALL(int, fchdir, int fd)
DEFINE_ENOSYS_SYSCALL(int, fchmod, int fd, mode_t mode)
DEFINE_ENOSYS_SYSCALL(int, fchmodat,
                      int dirfd, const char *pathname, mode_t mode, int flags)
DEFINE_ENOSYS_SYSCALL(int, fchown, int fd, uid_t owner, gid_t group)
DEFINE_ENOSYS_SYSCALL(int, fchownat,
                      int dirfd, const char *pathname,
                      uid_t owner, gid_t group, int flags)
DEFINE_ENOSYS_SYSCALL(int, flock, int fd, int operation)
DEFINE_ENOSYS_SYSCALL(pid_t, fork, void)
DEFINE_ENOSYS_SYSCALL(int, fstatat,
                      int dirfd, const char *pathname, struct stat *buf,
                      int flags)
DEFINE_ENOSYS_SYSCALL(int, ftruncate, int fd, off_t length)
DEFINE_ENOSYS_SYSCALL(int, ftruncate64, int fd, off64_t length)
DEFINE_ENOSYS_SYSCALL(int, getgroups, int size, gid_t list[])
DEFINE_ENOSYS_SYSCALL(int, getitimer, int which, struct itimerval *curr_value)
DEFINE_ENOSYS_SYSCALL(int, getpeername, int sockfd, struct sockaddr *addr,
                      socklen_t *addrlen)
DEFINE_ENOSYS_SYSCALL(pid_t, getpgid, pid_t pid)
DEFINE_ENOSYS_SYSCALL(pid_t, getppid, void)
DEFINE_ENOSYS_SYSCALL(int, getresgid, gid_t *rgid, gid_t *egid, gid_t *sgid)
DEFINE_ENOSYS_SYSCALL(int, getresuid, uid_t *ruid, uid_t *euid, uid_t *suid)
DEFINE_ENOSYS_SYSCALL(int, init_module,
                      void *module_image, unsigned long len,
                      const char *param_values)
DEFINE_ENOSYS_SYSCALL(int, getrusage, int who, struct rusage *usage)
DEFINE_ENOSYS_SYSCALL(int, getsockname, int sockfd, struct sockaddr *addr,
                      socklen_t *addrlen)
DEFINE_ENOSYS_SYSCALL(int, getsockopt, int sockfd, int level, int optname,
                      void *optval, socklen_t *optlen)
DEFINE_ENOSYS_SYSCALL(int, getrlimit, int resource, struct rlimit *rlim)
DEFINE_ENOSYS_SYSCALL(int, inotify_add_watch, int fd, const char *pathname,
                      uint32_t mask)
DEFINE_ENOSYS_SYSCALL(int, inotify_init, void)
DEFINE_ENOSYS_SYSCALL(int, inotify_rm_watch, int fd, uint32_t wd)
DEFINE_ENOSYS_SYSCALL(int, ioprio_get, int which, int who)
DEFINE_ENOSYS_SYSCALL(int, ioprio_set, int which, int who, int ioprio)
DEFINE_ENOSYS_SYSCALL(int, kill, pid_t pid, int sig)
DEFINE_ENOSYS_SYSCALL(int, klogctl, int type, char *bufp, int len)
DEFINE_ENOSYS_SYSCALL(int, lchown, const char *path, uid_t owner, gid_t group)
DEFINE_ENOSYS_SYSCALL(int, link, const char *oldpath, const char *newpath)
DEFINE_ENOSYS_SYSCALL(int, listen, int sockfd, int backlog)
DEFINE_ENOSYS_SYSCALL(int, madvise, const void *addr, size_t length,
                      int advice)
DEFINE_ENOSYS_SYSCALL(int, mincore, void *addr, size_t length,
                      unsigned char *vec)
DEFINE_ENOSYS_SYSCALL(int, mkdir, const char *pathname, mode_t mode)
DEFINE_ENOSYS_SYSCALL(int, mkdirat,
                      int dirfd, const char *pathname, mode_t mode)
DEFINE_ENOSYS_SYSCALL(int, mlock, const void *addr, size_t len)
DEFINE_ENOSYS_SYSCALL(int, mlockall, int flags)
DEFINE_ENOSYS_SYSCALL(int, mount, const char *source, const char *target,
                      const char *filesystemtype, unsigned long mountflags,
                      const void *data)
DEFINE_ENOSYS_SYSCALL(void *, mremap, void *old_address, size_t old_size,
                      size_t new_size, unsigned long flags)
DEFINE_ENOSYS_SYSCALL(int, msync, const void *addr, size_t length, int flags)
DEFINE_ENOSYS_SYSCALL(int, munlock, const void *addr, size_t len)
DEFINE_ENOSYS_SYSCALL(int, munlockall)
DEFINE_ENOSYS_SYSCALL(int, pause, void)
DEFINE_ENOSYS_SYSCALL(int, personality, unsigned long persona)
DEFINE_ENOSYS_SYSCALL(int, pipe, int pipefd[2])
DEFINE_ENOSYS_SYSCALL(int, prctl, int option, ...)
DEFINE_ENOSYS_SYSCALL(int, pthread_kill, pthread_t thread, int sig)
DEFINE_ENOSYS_SYSCALL(int, pthread_sigmask,
                      int how, const sigset_t *set, sigset_t *oldset)
DEFINE_ENOSYS_SYSCALL(int, readlink,
                      const char *path, char *buf, size_t bufsize)
DEFINE_ENOSYS_SYSCALL(int, readv, int fd, const struct iovec *iov, int iovcnt)
DEFINE_ENOSYS_SYSCALL(ssize_t, recvfrom, int sockfd, void *buf, size_t len,
                      uint32_t flags, const struct sockaddr *src_addr,
                      socklen_t *addrlen)
DEFINE_ENOSYS_SYSCALL(ssize_t, recvmsg, int sockfd, struct msghdr *msg,
                      unsigned int flags)
DEFINE_ENOSYS_SYSCALL(int, rename, const char *oldpath, const char *newpath)
DEFINE_ENOSYS_SYSCALL(int, renameat,
                      int olddirfd, const char *oldpath,
                      int newdirfd, const char *newpath)
DEFINE_ENOSYS_SYSCALL(int, rmdir, const char *pathname)
DEFINE_ENOSYS_SYSCALL(int, sched_getparam,
                      pid_t pid, struct sched_param *param)
DEFINE_ENOSYS_SYSCALL(int, sched_get_priority_max, int policy)
DEFINE_ENOSYS_SYSCALL(int, sched_get_priority_min, int policy)
DEFINE_ENOSYS_SYSCALL(int, sched_getscheduler, pid_t pid)
DEFINE_ENOSYS_SYSCALL(int, sched_rr_get_interval,
                      pid_t pid, struct timespec * tp)
DEFINE_ENOSYS_SYSCALL(int, sched_setscheduler,
                      pid_t pid, int policy, const struct sched_param *param)
DEFINE_ENOSYS_SYSCALL(int, sched_setparam,
                      pid_t pid, const struct sched_param *param)
DEFINE_ENOSYS_SYSCALL(int, select, int nfds, fd_set *readfds, fd_set *writefds,
                      fd_set *exceptfds, struct timeval *timeout)
DEFINE_ENOSYS_SYSCALL(ssize_t, sendfile, int out_fd, int in_fd,
                      off_t *offset, size_t count)
DEFINE_ENOSYS_SYSCALL(ssize_t, sendmsg, int sockfd, const struct msghdr *msg,
                      unsigned int flags)
DEFINE_ENOSYS_SYSCALL(ssize_t, sendto, int sockfd, const void *buf, size_t len,
                      int flags, const struct sockaddr *dest_addr,
                      socklen_t addrlen)
DEFINE_ENOSYS_SYSCALL(int, setgid, gid_t gid)
DEFINE_ENOSYS_SYSCALL(int, setgroups, size_t size, const gid_t *list)
DEFINE_ENOSYS_SYSCALL(int, setitimer, int which,
                      const struct itimerval *new_value,
                      struct itimerval *old_value)
DEFINE_ENOSYS_SYSCALL(int, setpgid, pid_t pid, pid_t pgid)
DEFINE_ENOSYS_SYSCALL(int, setpriority, int which, int who, int prio)
DEFINE_ENOSYS_SYSCALL(int, setregid, gid_t rgid, gid_t egid)
DEFINE_ENOSYS_SYSCALL(int, setresgid, gid_t rgid, gid_t egid, gid_t sgid)
DEFINE_ENOSYS_SYSCALL(int, setrlimit, int resource, const struct rlimit *rlim)
DEFINE_ENOSYS_SYSCALL(int, setsid, void)
DEFINE_ENOSYS_SYSCALL(int, setsockopt, int sockfd, int level, int optname,
                      const void *optval, socklen_t optlen)
DEFINE_ENOSYS_SYSCALL(int, settimeofday, const struct timeval *tv,
                      const struct timezone *tz)
DEFINE_ENOSYS_SYSCALL(int, sigaltstack, const stack_t *ss, stack_t *oss)
DEFINE_ENOSYS_SYSCALL(int, sigpending, sigset_t *set)
DEFINE_ENOSYS_SYSCALL(int, shutdown, int sockfd, int how)
DEFINE_ENOSYS_SYSCALL(int, sigaction, int signum, const struct sigaction *act,
                      struct sigaction *oldact)
DEFINE_ENOSYS_SYSCALL(int, sigprocmask,
                      int how, const sigset_t *set, sigset_t *oldset)
DEFINE_ENOSYS_SYSCALL(int, socket, int domain, int type, int protocol)
DEFINE_ENOSYS_SYSCALL(int, symlink, const char *oldpath, const char *newpath)
DEFINE_ENOSYS_SYSCALL(int, sync, void)
// Bare Metal mode has the direct syscall for internal use.
#if defined(__native_client__)
DEFINE_ENOSYS_SYSCALL(int, syscall, int number, ...)
#endif
DEFINE_ENOSYS_SYSCALL(int, sysinfo, struct sysinfo *info)
DEFINE_ENOSYS_SYSCALL(int, tkill, int tid, int sig)
DEFINE_ENOSYS_SYSCALL(int, tgkill, int tgid, int tid, int sig);
DEFINE_ENOSYS_SYSCALL(int, truncate, const char *path, off_t length)
DEFINE_ENOSYS_SYSCALL(int, truncate64, const char *path, off64_t length)
DEFINE_ENOSYS_SYSCALL(mode_t, umask, mode_t mask)
DEFINE_ENOSYS_SYSCALL(int, umount2, const char *target, int flags)
DEFINE_ENOSYS_SYSCALL(int, uname, struct utsname *buf)
DEFINE_ENOSYS_SYSCALL(int, unlinkat,
                      int dirfd, const char *pathname, int flags)
DEFINE_ENOSYS_SYSCALL(int, unshare, int flags)
DEFINE_ENOSYS_SYSCALL(int, utimes, const char *filename,
                      const struct timeval *times)
DEFINE_ENOSYS_SYSCALL(pid_t, vfork, void)
