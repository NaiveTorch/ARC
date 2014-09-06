// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMMON_VIRTUAL_FILE_SYSTEM_INTERFACE_H_
#define COMMON_VIRTUAL_FILE_SYSTEM_INTERFACE_H_

#include <dirent.h>
#include <netdb.h>
#include <poll.h>
#include <stdarg.h>
#include <stdint.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/vfs.h>
#include <unistd.h>
#include <utime.h>

#include <string>

namespace arc {

// An interface to all the file systems.
class VirtualFileSystemInterface {
 public:
  virtual ~VirtualFileSystemInterface() {}

  // Sorted by syscall name. Note that we should always prefer
  // 'const std::string&' over 'const char*' for a string parameter
  // which is always non-NULL.
  virtual int accept(int sockfd, struct sockaddr* addr, socklen_t* addrlen) = 0;
  virtual int access(const std::string& pathname, int mode) = 0;
  virtual int bind(int sockfd, const struct sockaddr* addr, socklen_t addrlen)
      = 0;
  virtual int chdir(const std::string& path) = 0;
  virtual int chown(const std::string& path, uid_t owner, gid_t group) = 0;
  virtual int close(int fd) = 0;
  virtual int connect(int sockfd, const struct sockaddr* addr,
                      socklen_t addrlen) = 0;
  virtual int dup(int oldfd) = 0;
  virtual int dup2(int oldfd, int newfd) = 0;
  virtual int epoll_create1(int flags) = 0;
  virtual int epoll_ctl(int epfd, int op, int fd, struct epoll_event* event)
      = 0;
  virtual int epoll_wait(int epfd, struct epoll_event* events, int maxevents,
                         int timeout) = 0;
  virtual int fcntl(int fd, int cmd, va_list v) = 0;
  virtual int fdatasync(int fd) = 0;
  virtual void freeaddrinfo(struct addrinfo* res) = 0;
  virtual int fstat(int fd, struct stat* buf) = 0;
  virtual int fsync(int fd) = 0;
  virtual int ftruncate(int fd, off64_t length) = 0;
  virtual int getaddrinfo(const char* node,  // NULL is allowed.
                          const char* service,  // NULL is allowed.
                          const struct addrinfo* hints,
                          struct addrinfo** res) = 0;
  virtual char* getcwd(char* buf,  // NULL is allowed.
                       size_t size) = 0;
  virtual int getdents(int fd, struct dirent* dirp, unsigned int count) = 0;
  virtual struct hostent* gethostbyaddr(
      const void* addr, socklen_t len, int type) = 0;
  virtual struct hostent* gethostbyname(const char* hostname) = 0;
  virtual int gethostbyname_r(
        const char* hostname, struct hostent* ret,
        char* buf, size_t buflen,
        struct hostent** result, int* h_errnop) = 0;
  virtual struct hostent* gethostbyname2(const char* hostname, int family) = 0;
  virtual int gethostbyname2_r(
      const char* hostname, int family, struct hostent* ret,
      char* buf, size_t buflen,
      struct hostent** result, int* h_errnop) = 0;
  virtual int getnameinfo(const sockaddr* sa, socklen_t salen,
                          char* host,  // NULL is allowed.
                          size_t hostlen,
                          char* serv,  // NULL is allowed.
                          size_t servlen, int flags) = 0;
  virtual int getsockname(int sockfd, struct sockaddr* addr, socklen_t* addrlen)
      = 0;
  virtual int getsockopt(int sockfd, int level, int optname, void* optval,
                         socklen_t* optlen) = 0;
  virtual int ioctl(int fd, int request, va_list v) = 0;
  virtual int listen(int sockfd, int backlog) = 0;
  virtual off64_t lseek(int fd, off64_t offset, int whence) = 0;
  virtual int lstat(const std::string& path, struct stat* buf) = 0;
  virtual int mkdir(const std::string& pathname, mode_t mode) = 0;
  virtual void* mmap(
      void* addr, size_t length, int prot, int flags, int fd, off_t offset) = 0;

  // In addition to the standard error numbers, these two functions set ENOSYS
  // in errno when [addr, addr+length) is not managed by posix_translation. In
  // that case, caller should call libc's ::mprotect or ::munmap with the same
  // parameters as a fallback.
  // TODO(crbug.com/362862): Remove the comment once crbug.com/362862 is fixed.
  virtual int mprotect(const void* addr, size_t length, int prot) = 0;
  virtual int munmap(void* addr, size_t length) = 0;

  virtual int open(const std::string& pathname, int oflag,
                   mode_t cmode) = 0;
  virtual int pipe2(int pipefd[2], int flags) = 0;
  virtual int poll(struct pollfd* fds, nfds_t nfds, int timeout) = 0;
  virtual ssize_t pread(int fd, void* buf, size_t count, off64_t offset) = 0;
  virtual ssize_t pwrite(
      int fd, const void* buf, size_t count, off64_t offset) = 0;
  virtual ssize_t read(int fd, void* buf, size_t count) = 0;
  virtual ssize_t readlink(const std::string& path, char* buf,
                           size_t bufsiz) = 0;
  virtual ssize_t readv(int fd, const struct iovec* iovec, int count) = 0;
  virtual char* realpath(const char* path,  // NULL is allowed
                         char* resolved_path /* NULL is allowed */) = 0;
  virtual ssize_t recv(int sockfd, void* buf, size_t len, int flags) = 0;
  virtual ssize_t recvfrom(int sockfd, void* buf, size_t len, int flags,
                           struct sockaddr* src_addr, socklen_t* addrlen) = 0;
  virtual ssize_t recvmsg(int sockfd, struct msghdr* msg, int flags) = 0;
  virtual int remove(const std::string& pathname) = 0;
  virtual int rename(const std::string& oldpath,
                     const std::string& newpath) = 0;
  virtual int rmdir(const std::string& pathname) = 0;
  virtual int select(int nfds, fd_set* readfds, fd_set* writefds,
                     fd_set* exceptfds, struct timeval* timeout) = 0;
  virtual ssize_t send(int sockfd, const void* buf, size_t len, int flags) = 0;
  virtual ssize_t sendto(int sockfd, const void* buf, size_t len, int flags,
                         const struct sockaddr* dest_addr, socklen_t addrlen)
      = 0;
  virtual ssize_t sendmsg(int sockfd, const struct msghdr* msg, int flags) = 0;
  virtual int setsockopt(int sockfd, int level, int optname, const void* optval,
                         socklen_t optlen) = 0;
  virtual int shutdown(int sockfd, int how) = 0;
  virtual int socket(int domain, int type, int protocol) = 0;
  virtual int socketpair(int domain, int type, int protocol, int sv[2]) = 0;
  virtual int stat(const std::string& path, struct stat* buf) = 0;
  virtual int statfs(const std::string& path, struct statfs* buf) = 0;
  virtual int statvfs(const std::string& path, struct statvfs* buf) = 0;
  virtual int truncate(const std::string& path, off64_t length) = 0;
  virtual mode_t umask(mode_t mask) = 0;
  virtual int unlink(const std::string& pathname) = 0;
  virtual int utime(const std::string& pathname,
                    const struct utimbuf* times) = 0;
  virtual int utimes(const std::string& pathname,
                     const struct timeval times[2]) = 0;
  virtual ssize_t write(int fd, const void* buf, size_t count) = 0;
  virtual ssize_t writev(int fd, const struct iovec* iovec, int count) = 0;
};

}  // namespace arc
#endif  // COMMON_VIRTUAL_FILE_SYSTEM_INTERFACE_H_
