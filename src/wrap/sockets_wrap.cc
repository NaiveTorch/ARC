/* Copyright 2014 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Simple wrappers for various socket calls.
 */

#include <errno.h>
#include <netdb.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/epoll.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>

#include "common/arc_strace.h"
#include "common/danger.h"
#include "common/plugin_handle.h"
#include "common/virtual_file_system_interface.h"
#include "wrap/file_wrap_private.h"

extern "C" {
int __wrap_accept(int sockfd, struct sockaddr* addr, socklen_t* addrlen);
int __wrap_bind(int sockfd, const struct sockaddr* addr, socklen_t addrlen);
int __wrap_connect(int sockfd, const struct sockaddr* addr,
                   socklen_t addrlen);
int __wrap_epoll_create(int size);
int __wrap_epoll_ctl(int epfd, int op, int fd, struct epoll_event* event);
int __wrap_epoll_wait(int epfd, struct epoll_event* events, int maxevents,
                      int timeout);
void __wrap_freeaddrinfo(struct addrinfo* res);
const char* __wrap_gai_strerror(int errcode);
int __wrap_getaddrinfo(const char* node, const char* service,
                       const struct addrinfo* hints, struct addrinfo** res);
struct hostent* __wrap_gethostbyaddr(
    const void* addr, socklen_t len, int type);
struct hostent* __wrap_gethostbyname(const char* hostname);
struct hostent* __wrap_gethostbyname2(const char* hostname, int family);
int __wrap_gethostbyname_r(const char* hostname, struct hostent* ret,
                           char* buf, size_t buflen,
                           struct hostent** result, int* h_errnop);
int __wrap_getnameinfo(const struct sockaddr* sa, socklen_t salen,
                       char* host, size_t hostlen,
                       char* serv, size_t servlen, int flags);
int __wrap_getpeername(int sockfd, struct sockaddr* addr,
                       socklen_t* addrlen);
int __wrap_getsockname(int sockfd, struct sockaddr* addr,
                       socklen_t* addrlen);
int __wrap_getsockopt(int sockfd, int level, int optname,
                      void* optval, socklen_t* optlen);
int __wrap_listen(int sockfd, int backlog);
int __wrap_pipe(int pipefd[2]);
int __wrap_pipe2(int pipefd[2], int flags);
int __wrap_pselect(int nfds, fd_set* readfds, fd_set* writefds,
                   fd_set* exceptfds, const struct timespec* timeout,
                   const sigset_t* sigmask);
ssize_t __wrap_recv(int sockfd, void* buf, size_t len, int flags);
ssize_t __wrap_recvfrom(int sockfd, void* buf, size_t len, int flags,
                        struct sockaddr* src_addr, socklen_t* addrlen);
ssize_t __wrap_recvmsg(int sockfd, struct msghdr* msg, int flags);
int __wrap_select(int nfds, fd_set* readfds, fd_set* writefds,
                  fd_set* exceptfds, struct timeval* timeout);
ssize_t __wrap_send(int sockfd, const void* buf, size_t len, int flags);
ssize_t __wrap_sendto(int sockfd, const void* buf, size_t len, int flags,
                      const struct sockaddr* dest_addr, socklen_t addrlen);
ssize_t __wrap_sendmsg(int sockfd, const struct msghdr* msg, int flags);
int __wrap_setsockopt(int sockfd, int level, int optname,
                      const void* optval, socklen_t optlen);
int __wrap_shutdown(int sockfd, int how);
int __wrap_socket(int domain, int type, int protocol);
int __wrap_socketpair(int domain, int type, int protocol, int sv[2]);
}  // extern "C"

// This file does not have special cases for LIBWRAP_FOR_TEST because our unit
// tests do not call these socket functions at all.

int __wrap_accept(int sockfd, struct sockaddr* addr, socklen_t* addrlen) {
  ARC_STRACE_ENTER_FD("accept", "%d, %p, %p", sockfd, addr, addrlen);
  arc::PluginHandle handle;
  int fd = handle.GetVirtualFileSystem()->accept(sockfd, addr, addrlen);
  ARC_STRACE_REGISTER_FD(fd, "accept");
  ARC_STRACE_RETURN(fd);
}

int __wrap_bind(int sockfd, const struct sockaddr* addr, socklen_t addrlen) {
  ARC_STRACE_ENTER_FD("bind", "%d, %s, %u",
                      sockfd, arc::GetSockaddrStr(addr).c_str(), addrlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->bind(sockfd, addr, addrlen);
  ARC_STRACE_RETURN(result);
}

int __wrap_connect(int sockfd, const struct sockaddr* addr,
                   socklen_t addrlen) {
  ARC_STRACE_ENTER_FD("connect", "%d, %s, %u",
                      sockfd, arc::GetSockaddrStr(addr).c_str(), addrlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->connect(sockfd, addr, addrlen);
  ARC_STRACE_RETURN(result);
}

int __wrap_epoll_create(int size) {
  ARC_STRACE_ENTER("epoll_create", "%d", size);
  arc::PluginHandle handle;
  int fd = handle.GetVirtualFileSystem()->epoll_create1(0);
  ARC_STRACE_REGISTER_FD(fd, "epoll");
  ARC_STRACE_RETURN(fd);
}

int __wrap_epoll_ctl(int epfd, int op, int fd, struct epoll_event* event) {
  ARC_STRACE_ENTER_FD("epoll_ctl", "%d, %d, %d, %p", epfd, op, fd, event);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->epoll_ctl(epfd, op, fd, event);
  ARC_STRACE_RETURN(result);
}

int __wrap_epoll_wait(int epfd, struct epoll_event* events, int maxevents,
                      int timeout) {
  ARC_STRACE_ENTER_FD("epoll_wait", "%d, %p, %d, %d",
                      epfd, events, maxevents, timeout);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->epoll_wait(epfd, events,
                                                         maxevents, timeout);
  ARC_STRACE_RETURN(result);
}

void __wrap_freeaddrinfo(struct addrinfo* res) {
  ARC_STRACE_ENTER("freeaddrinfo", "%p", res);
  arc::PluginHandle handle;
  handle.GetVirtualFileSystem()->freeaddrinfo(res);
  ARC_STRACE_RETURN_VOID();
}

int __wrap_getnameinfo(const struct sockaddr* sa, socklen_t salen,
                       char* host, size_t hostlen,
                       char* serv, size_t servlen, int flags) {
  // TODO(igorc): Add GetNameInfoFlagStr() to src/common/arc_strace.[h,cc].
  ARC_STRACE_ENTER("getnameinfo", "%p, %d, %p, %zu, %p, %zu, %d",
                   sa, salen, host, hostlen, serv, servlen, flags);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->getnameinfo(
      sa, salen, host, hostlen, serv, servlen, flags);
  ARC_STRACE_RETURN(result);
}

int __wrap_getaddrinfo(const char* node, const char* service,
                       const struct addrinfo* hints, struct addrinfo** res) {
  ARC_STRACE_ENTER("getaddrinfo", "\"%s\", \"%s\", %p, %p",
                   SAFE_CSTR(node), SAFE_CSTR(service), hints, res);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->getaddrinfo(
      node, service, hints, res);
  // TODO(crbug.com/241955): Show errno for EAI_SYSTEM?
  ARC_STRACE_RETURN(result);
}

const char* __wrap_gai_strerror(int errcode) {
  // This code duplicates bionic/libc/netbsd/net/getaddrinfo.c.
  // TODO(crbug.com/356271): Use Bionic impl instead.
  static const char* const kErrorList[] = {
    "Success",
    "Address family for hostname not supported",    /* EAI_ADDRFAMILY */
    "Temporary failure in name resolution",         /* EAI_AGAIN      */
    "Invalid value for ai_flags",                   /* EAI_BADFLAGS   */
    "Non-recoverable failure in name resolution",   /* EAI_FAIL       */
    "ai_family not supported",                      /* EAI_FAMILY     */
    "Memory allocation failure",                    /* EAI_MEMORY     */
    "No address associated with hostname",          /* EAI_NODATA     */
    "hostname nor servname provided, or not known", /* EAI_NONAME     */
    "servname not supported for ai_socktype",       /* EAI_SERVICE    */
    "ai_socktype not supported",                    /* EAI_SOCKTYPE   */
    "System error returned in errno",               /* EAI_SYSTEM     */
    "Invalid value for hints",                      /* EAI_BADHINTS   */
    "Resolved protocol is unknown",                 /* EAI_PROTOCOL   */
    "Argument buffer overflow",                     /* EAI_OVERFLOW   */
    "Unknown error",                                /* EAI_MAX        */
  };

  ALOG_ASSERT((sizeof(kErrorList) / sizeof(kErrorList[0])) == (EAI_MAX + 1));

  if (errcode < 0 || errcode > EAI_MAX)
    errcode = EAI_MAX;
  return kErrorList[errcode];
}

struct hostent* __wrap_gethostbyaddr(
    const void* addr, socklen_t len, int type) {
  // TODO(igorc): Add GetNetFamilyStr() to src/common/arc_strace.[h,cc].
  ARC_STRACE_ENTER("gethostbyaddr", "%p, %d, %d", addr, len, type);
  arc::PluginHandle handle;
  struct hostent* result = handle.GetVirtualFileSystem()->gethostbyaddr(
      addr, len, type);
  if (result == NULL) {
    ARC_STRACE_REPORT("h_errno=%d", h_errno);
  }
  ARC_STRACE_RETURN_PTR(result, false);
}

struct hostent* __wrap_gethostbyname(const char* hostname) {
  ARC_STRACE_ENTER("gethostbyname", "\"%s\"", SAFE_CSTR(hostname));
  arc::PluginHandle handle;
  struct hostent* result = handle.GetVirtualFileSystem()->gethostbyname(
      hostname);
  if (result == NULL) {
    ARC_STRACE_REPORT("h_errno=%d", h_errno);
  }
  ARC_STRACE_RETURN_PTR(result, false);
}

int __wrap_gethostbyname_r(const char* hostname, struct hostent* ret,
                           char* buf, size_t buflen,
                           struct hostent** result, int* h_errnop) {
  ARC_STRACE_ENTER("gethostbyname_r", "\"%s\"", SAFE_CSTR(hostname));
  arc::PluginHandle handle;
  int res = handle.GetVirtualFileSystem()
      ->gethostbyname_r(hostname, ret, buf, buflen, result, h_errnop);
  if (res != 0 && *h_errnop != 0) {
    ARC_STRACE_REPORT("h_errno=%d", *h_errnop);
  }
  ARC_STRACE_RETURN(res);
}

struct hostent* __wrap_gethostbyname2(const char* hostname, int family) {
  ARC_STRACE_ENTER("gethostbyname2", "\"%s\" %d",
                   SAFE_CSTR(hostname), family);
  arc::PluginHandle handle;
  struct hostent* result = handle.GetVirtualFileSystem()
      ->gethostbyname2(hostname, family);
  if (result == NULL) {
    ARC_STRACE_REPORT("h_errno=%d", h_errno);
  }
  ARC_STRACE_RETURN_PTR(result, false);
}

int __wrap_getpeername(int sockfd, struct sockaddr* addr,
                       socklen_t* addrlen) {
  ARC_STRACE_ENTER_FD("getpeername", "%d, %p, %p", sockfd, addr, addrlen);
  DANGERF("getpeername: sockfd=%d", sockfd);
  ARC_STRACE_REPORT("not implemented yet");
  errno = EBADF;
  ARC_STRACE_RETURN(-1);
}

int __wrap_getsockname(int sockfd, struct sockaddr* addr,
                       socklen_t* addrlen) {
  ARC_STRACE_ENTER_FD("getsockname", "%d, %p, %p", sockfd, addr, addrlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->getsockname(
      sockfd, addr, addrlen);
  if (result == -1 && errno == EINVAL) {
    DANGER();
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_getsockopt(int sockfd, int level, int optname,
                      void* optval, socklen_t* optlen) {
  ARC_STRACE_ENTER_FD("getsockopt", "%d, %d, %d, %p, %p",
                      sockfd, level, optname, optval, optlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->getsockopt(
      sockfd, level, optname, optval, optlen);
  ARC_STRACE_RETURN(result);
}

int __wrap_listen(int sockfd, int backlog) {
  ARC_STRACE_ENTER_FD("listen", "%d, %d", sockfd, backlog);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->listen(sockfd, backlog);
  ARC_STRACE_RETURN(result);
}

int __wrap_pipe(int pipefd[2]) {
  ARC_STRACE_ENTER("pipe", "%p", pipefd);
  arc::PluginHandle handle;
  int result;
  result = handle.GetVirtualFileSystem()->pipe2(pipefd, 0);
  if (result >= 0) {
    ARC_STRACE_REGISTER_FD(pipefd[0], "pipe[0]");
    ARC_STRACE_REGISTER_FD(pipefd[1], "pipe[1]");
    ARC_STRACE_REPORT("pipe[0]=%d pipe[1]=%d", pipefd[0], pipefd[1]);
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_pipe2(int pipefd[2], int flags) {
  ARC_STRACE_ENTER("pipe2", "%p, %d", pipefd, flags);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->pipe2(pipefd, flags);
  if (result >= 0) {
    ARC_STRACE_REGISTER_FD(pipefd[0], "pipe2[0]");
    ARC_STRACE_REGISTER_FD(pipefd[1], "pipe2[1]");
    ARC_STRACE_REPORT("pipe[0]=%d pipe[1]=%d", pipefd[0], pipefd[1]);
  }
  ARC_STRACE_RETURN(result);
}

int __wrap_pselect(int nfds, fd_set* readfds, fd_set* writefds,
                   fd_set* exceptfds, const struct timespec* timeout,
                   const sigset_t* sigmask) {
  ALOG_ASSERT(false, "pselect is not supported");
  errno = EAFNOSUPPORT;
  return -1;
}

ssize_t __wrap_recv(int sockfd, void* buf, size_t len, int flags) {
  ARC_STRACE_ENTER_FD("recv", "%d, %p, %zu, %d", sockfd, buf, len, flags);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->recv(sockfd, buf, len, flags);
  if (result >= 0)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_recvfrom(int sockfd, void* buf, size_t len, int flags,
                        struct sockaddr* src_addr, socklen_t* addrlen) {
  ARC_STRACE_ENTER_FD("recvfrom", "%d, %p, %zu, %d, %p, %p",
                      sockfd, buf, len, flags, src_addr, addrlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->recvfrom(sockfd, buf, len, flags,
                                                       src_addr, addrlen);
  if (result == -1 && errno == EINVAL) {
    DANGER();
  }
  if (result >= 0)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_recvmsg(int sockfd, struct msghdr* msg, int flags) {
  ARC_STRACE_ENTER_FD("recvmsg", "%d, %p, %d", sockfd, msg, flags);
  arc::PluginHandle handle;
  ssize_t result = handle.GetVirtualFileSystem()->recvmsg(sockfd, msg, flags);
  ARC_STRACE_RETURN(result);
}

int __wrap_select(int nfds, fd_set* readfds, fd_set* writefds,
                  fd_set* exceptfds, struct timeval* timeout) {
  ARC_STRACE_ENTER("select", "%d, %p, %p, %p, %p",
                   nfds, readfds, writefds, exceptfds, timeout);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->select(nfds, readfds, writefds,
                                                     exceptfds, timeout);
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_send(int sockfd, const void* buf, size_t len, int flags) {
  ARC_STRACE_ENTER_FD("send", "%d, %p, %zu, %d", sockfd, buf, len, flags);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->send(sockfd, buf, len, flags);
  if (errno != EFAULT)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_sendto(int sockfd, const void* buf, size_t len, int flags,
                      const struct sockaddr* dest_addr, socklen_t addrlen) {
  ARC_STRACE_ENTER_FD("sendto", "%d, %p, %zu, %d, %s, %u",
                      sockfd, buf, len, flags,
                      arc::GetSockaddrStr(dest_addr).c_str(), addrlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->sendto(sockfd, buf, len, flags,
                                                     dest_addr, addrlen);
  if (result == -1 && errno == EINVAL) {
    DANGER();
  }
  if (errno != EFAULT)
    ARC_STRACE_REPORT("buf=%s", arc::GetRWBufStr(buf, result).c_str());
  ARC_STRACE_RETURN(result);
}

ssize_t __wrap_sendmsg(int sockfd, const struct msghdr* msg, int flags) {
  ARC_STRACE_ENTER_FD("sendmsg", "%d, %p, %d", sockfd, msg, flags);
  arc::PluginHandle handle;
  ssize_t result = handle.GetVirtualFileSystem()->sendmsg(sockfd, msg, flags);
  ARC_STRACE_RETURN(result);
}

int __wrap_setsockopt(int sockfd, int level, int optname,
                      const void* optval, socklen_t optlen) {
  ARC_STRACE_ENTER_FD("setsockopt", "%d, %d, %d, %p, %d",
                      sockfd, level, optname, optval, optlen);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->setsockopt(sockfd, level, optname,
                                                         optval, optlen);
  ARC_STRACE_RETURN(result);
}

int __wrap_shutdown(int sockfd, int how) {
  ARC_STRACE_ENTER_FD("shutdown", "%d, %d", sockfd, how);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->shutdown(sockfd, how);
  ARC_STRACE_RETURN(result);
}

int __wrap_socket(int domain, int type, int protocol) {
  ARC_STRACE_ENTER("socket", "%s, %s, %s",
                   arc::GetSocketDomainStr(domain).c_str(),
                   arc::GetSocketTypeStr(type).c_str(),
                   arc::GetSocketProtocolStr(protocol).c_str());
  arc::PluginHandle handle;
  int fd = handle.GetVirtualFileSystem()->socket(domain, type, protocol);
  ARC_STRACE_REGISTER_FD(fd, "socket");
  ARC_STRACE_RETURN(fd);
}

int __wrap_socketpair(int domain, int type, int protocol, int sv[2]) {
  ARC_STRACE_ENTER("socketpair", "%s, %s, %s, %p",
                   arc::GetSocketDomainStr(domain).c_str(),
                   arc::GetSocketTypeStr(type).c_str(),
                   arc::GetSocketProtocolStr(protocol).c_str(),
                   sv);
  arc::PluginHandle handle;
  int result = handle.GetVirtualFileSystem()->socketpair(
      domain, type, protocol, sv);
  if (result >= 0) {
    ARC_STRACE_REGISTER_FD(sv[0], "socketpair[0]");
    ARC_STRACE_REGISTER_FD(sv[1], "socketpair[1]");
    ARC_STRACE_REPORT("sock[0]=%d sock[1]=%d", sv[0], sv[1]);
  }
  ARC_STRACE_RETURN(result);
}
