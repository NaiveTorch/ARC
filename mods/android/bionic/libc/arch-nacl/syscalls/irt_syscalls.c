// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/irt_syscalls.c"
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <nacl_stat.h>
// ARC MOD BEGIN
// Add some include files.
#if defined(BARE_METAL_BIONIC)
#include <bare_metal/common/bare_metal_irt.h>
#endif
#include <irt_syscalls.h>
#include <irt.h>
#include <irt_dev.h>
#include <irt_nonsfi.h>
#include <private/at_sysinfo.h>
#include <private/dl_dst_lib.h>

// Remove unnecessary functions which call NaCl syscalls directly.

// Define variables.

// Two macros to minimize the difference between the upstream code and
// this code.
#define off_t nacl_abi_off_t
#define socklen_t nacl_abi_socklen_t
// ARC MOD END

/* Load files from DL_DST_LIB using IRT's open_resource. Other paths
   will be processed using regular open syscall.

   Note: nacl_mount may change this logic if needed.  */
static int (*___nacl_irt_open_resource) (const char* file, int *fd);
static int nacl_irt_open_resource (const char *pathname, int *newfd) {
  if (memcmp (DL_DST_LIB "/", pathname, sizeof (DL_DST_LIB)))
    return __nacl_irt_open (pathname, O_RDONLY, 0, newfd);
  else
    return ___nacl_irt_open_resource (pathname + sizeof (DL_DST_LIB) - 1,
                                      newfd);
}

// ARC MOD BEGIN
// Remove unnecessary functions which call NaCl syscalls directly.
// ARC MOD END

static size_t no_interface (const char *interface_ident,
                            void *table, size_t tablesize) {
  return 0;
}

static int not_implemented() {
  return (38 /* ENOSYS */);
}

size_t (*__nacl_irt_query) (const char *interface_ident,
                            void *table, size_t tablesize);
// ARC MOD BEGIN
#ifdef BARE_METAL_BIONIC
// For Bare Metal Mode, we'll inject irt_open_resource. It is necessary
// to run the arc, but it is not yet developed. This just fills the gap.
// TODO(crbug.com/354290): Remove the code when irt_resource_open is actually
// implemented.

// Original irt_query pointer.
static size_t (*___nacl_irt_query) (const char *interface_ident,
                                    void *table, size_t tablesize);

// If available, we'd like to use real irt_open_resource() implementation.
// So, keep the pointer.
static int (*__nacl_irt_open_resource_real) (const char *pathname,
                                             int *newfd);

// The injected version of irt_open_resource opens a local file directly.
// However, __nacl_irt_open will be wrapped by file_wrap.cc later, so we keep
// its raw pointer here.
static int (*__nacl_irt_open_real) (const char *pathname, int oflag,
                                    mode_t cmode, int *newfd);

// Instead of real implementation of irt_open_resource, we use local files for
// the demo.
static int nacl_irt_open_resource_injected(const char *pathname, int *newfd) {
  // If available try the real open resource first.
  if (__nacl_irt_open_resource_real) {
    int error = __nacl_irt_open_resource_real(pathname, newfd);
    if (error != ENOSYS)
      return error;
  }

#if defined(__i386__)
// As this string will be used as a part of an ARC's target name
// (e.g., bare_metal_i686), this must be "i686", not "i386".
#define ARCH "i686"
#elif defined(__arm__)
#define ARCH "arm"
#else
#error "Unknown CPU architecture!"
#endif

  // Rewrite the path to local file name. There are two cases to reach here.
  // 1) Called from the loader to load shared object files.
  // 2) Called from NaClManifestFile.
  // The given path name will be different for each case, and that's why
  // some files have different paths (such as "/main.nexe" and "main.nexe").
  char realpath[256] =
#if defined(__arm__)
      "/var/tmp/arc/"
#endif
      ARC_TARGET_PATH "/runtime/"
      "_platform_specific/bare_metal_" ARCH "/";

  // Get the basename (without basename, which libc_common.a does not have).
  const char* found = strrchr(pathname, '/');
  if (found)
    pathname = found + 1;

  if (!strcmp(pathname, "main.nexe")) {
    strcat(realpath, "arc_bare_metal_" ARCH ".nexe");
  } else if (!strcmp(pathname, "readonly_fs_image.img")) {
    strcat(realpath, "readonly_fs_image.img");
  } else if (!strcmp(pathname, "audio_policy.default.so") ||
             !strcmp(pathname, "audio.primary.arc.so") ||
             !strcmp(pathname, "gralloc.arc.so") ||
             !strcmp(pathname, "gralloc.default.so") ||
             !strcmp(pathname, "local_time.default.so")) {
    strcat(strcat(realpath, "hw/"), pathname);
  } else if (!strcmp(pathname, "libEGL_emulation.so") ||
             !strcmp(pathname, "libGLESv1_CM_emulation.so") ||
             !strcmp(pathname, "libGLES_android.so") ||
             !strcmp(pathname, "libGLESv2_emulation.so") ||
             !strcmp(pathname, "egl.cfg")) {
    strcat(strcat(realpath, "egl/"), pathname);
  } else if (!strcmp(pathname, "libbundlewrapper.so") ||
             !strcmp(pathname, "libdownmix.so") ||
             !strcmp(pathname, "libreverbwrapper.so") ||
             !strcmp(pathname, "libvisualizer.so")) {
    strcat(strcat(realpath, "soundfx/"), pathname);
  } else {
    strcat(realpath, pathname);
  }

  return __nacl_irt_open_real(realpath, O_RDONLY, 0, newfd);
}

static size_t nacl_irt_query(const char *interface_ident,
                             void *table, size_t tablesize) {
  size_t result = ___nacl_irt_query(interface_ident, table, tablesize);
  if (strcmp(interface_ident, NACL_IRT_RESOURCE_OPEN_v0_1))
    return result;

  if (tablesize < sizeof(struct nacl_irt_resource_open))
    return 0;

  if (result > 0 && __nacl_irt_open_resource_real == NULL) {
    __nacl_irt_open_resource_real =
        ((struct nacl_irt_resource_open *)table)->open_resource;
  }

  // If obtaining nacl_irt_open_resource fails, it means we are
  // running unittests. For this case, open_resource call should fail.
  struct nacl_irt_resource_open irt_resource_open_injected = {
    result ? nacl_irt_open_resource_injected : not_implemented
  };
  memcpy(table, &irt_resource_open_injected,
         sizeof(struct nacl_irt_resource_open));
  return sizeof(struct nacl_irt_resource_open);
}

#endif

static int not_implemented_open(const char *pathname, int oflag, mode_t cmode,
                                int *newfd) {
  return ENOSYS;
}

// ARC MOD END
int (*__nacl_irt_mkdir) (const char* pathname, mode_t mode);
int (*__nacl_irt_rmdir) (const char* pathname);
int (*__nacl_irt_chdir) (const char* pathname);
int (*__nacl_irt_getcwd) (char* buf, size_t size);

void (*__nacl_irt_exit) (int status);
int (*__nacl_irt_gettod) (struct timeval *tv);
int (*__nacl_irt_clock) (clock_t *ticks);
// ARC MOD BEGIN UPSTREAM nacl-use-abi-timespec
int (*__nacl_irt_nanosleep) (const struct nacl_abi_timespec *req, struct nacl_abi_timespec *rem);
// ARC MOD END UPSTREAM
int (*__nacl_irt_sched_yield) (void);
int (*__nacl_irt_sysconf) (int name, int *value);

int (*__nacl_irt_open) (const char *pathname, int oflag, mode_t cmode,
                        int *newfd);
int (*__nacl_irt_close) (int fd);
int (*__nacl_irt_read) (int fd, void *buf, size_t count, size_t *nread);
int (*__nacl_irt_write) (int fd, const void *buf, size_t count,
                         size_t *nwrote);
int (*__nacl_irt_seek) (int fd, off_t offset, int whence, off_t *new_offset);
int (*__nacl_irt_dup) (int fd, int *newfd);
int (*__nacl_irt_dup2) (int fd, int newfd);
int (*__nacl_irt_fstat) (int fd, struct nacl_abi_stat *);
int (*__nacl_irt_stat) (const char *pathname, struct nacl_abi_stat *);
int (*__nacl_irt_getdents) (int fd, struct dirent *, size_t count,
                            size_t *nread);
int (*__nacl_irt_socket) (int domain, int type, int protocol, int *sd);
int (*__nacl_irt_accept) (int sockfd, struct sockaddr *addr,
                          socklen_t *addrlen, int *sd);
int (*__nacl_irt_bind) (int sockfd, const struct sockaddr *addr,
                        socklen_t addrlen);
int (*__nacl_irt_listen) (int sockfd, int backlog);
int (*__nacl_irt_connect) (int sockfd, const struct sockaddr *addr,
                           socklen_t addrlen);
int (*__nacl_irt_send) (int sockfd, const void *buf, size_t len, int flags,
                        int *count);
int (*__nacl_irt_sendmsg) (int sockfd, const struct msghdr *msg, int flags,
                           int *count);
int (*__nacl_irt_sendto) (int sockfd, const void *buf, size_t len, int flags,
                          const struct sockaddr *dest_addr, socklen_t addrlen,
                          int *count);
int (*__nacl_irt_recv) (int sockfd, void *buf, size_t len, int flags,
                        int *count);
int (*__nacl_irt_recvmsg) (int sockfd, struct msghdr *msg, int flags,
                           int *count);
int (*__nacl_irt_recvfrom) (int sockfd, void *buf, size_t len, int flags,
                            struct sockaddr *dest_addr, socklen_t* addrlen,
                            int *count);

int (*__nacl_irt_epoll_create) (int size, int *fd);
int (*__nacl_irt_epoll_create1) (int flags, int *fd);
int (*__nacl_irt_epoll_ctl) (int epfd, int op, int fd,
                             struct epoll_event *event);
int (*__nacl_irt_epoll_pwait) (int epfd, struct epoll_event *events,
                               int maxevents, int timeout,
                               const sigset_t *sigmask, size_t sigset_size,
                               int *count);
int (*__nacl_irt_epoll_wait) (int epfd, struct epoll_event *events,
                              int maxevents, int timeout, int *count);
int (*__nacl_irt_poll) (struct pollfd *fds, nfds_t nfds,
                        int timeout, int *count);
int (*__nacl_irt_ppoll) (struct pollfd *fds, nfds_t nfds,
                         // ARC MOD BEGIN UPSTREAM nacl-use-abi-timespec
                         const struct nacl_abi_timespec *timeout,
                         // ARC MOD END UPSTREAM
                         const sigset_t *sigmask,
                         size_t sigset_size, int *count);
int (*__nacl_irt_select) (int nfds, fd_set *readfds,
                          fd_set *writefds, fd_set *exceptfds,
                          const struct timeval *timeout,
                          int *count);
int (*__nacl_irt_pselect) (int nfds, fd_set *readfds,
                           fd_set *writefds, fd_set *exceptfds,
                           const struct timeval *timeout,
                           void* sigmask, int *count);
int (*__nacl_irt_getpeername) (int sockfd, struct sockaddr *addr,
                               socklen_t *addrlen);
int (*__nacl_irt_getsockname) (int sockfd, struct sockaddr *addr,
                               socklen_t *addrlen);
int (*__nacl_irt_getsockopt) (int sockfd, int level, int optname,
                              void *optval, socklen_t *optlen);
int (*__nacl_irt_setsockopt) (int sockfd, int level, int optname,
                              const void *optval, socklen_t optlen);
int (*__nacl_irt_socketpair) (int domain, int type, int protocol, int sv[2]);
int (*__nacl_irt_shutdown) (int sockfd, int how);


int (*__nacl_irt_sysbrk) (void **newbrk);
int (*__nacl_irt_mmap) (void **addr, size_t len, int prot, int flags,
                        int fd, off_t off);
int (*__nacl_irt_munmap) (void *addr, size_t len);
int (*__nacl_irt_mprotect) (void *addr, size_t len, int prot);

int (*__nacl_irt_dyncode_create) (void *dest, const void *src, size_t size);
int (*__nacl_irt_dyncode_modify) (void *dest, const void *src, size_t size);
int (*__nacl_irt_dyncode_delete) (void *dest, size_t size);

int (*__nacl_irt_thread_create) (void (*start_user_address)(void),
                                 void *stack,
                                 void *thread_ptr);
void (*__nacl_irt_thread_exit) (int32_t *stack_flag);
int (*__nacl_irt_thread_nice) (const int nice);

int (*__nacl_irt_mutex_create) (int *mutex_handle);
int (*__nacl_irt_mutex_destroy) (int mutex_handle);
int (*__nacl_irt_mutex_lock) (int mutex_handle);
int (*__nacl_irt_mutex_unlock) (int mutex_handle);
int (*__nacl_irt_mutex_trylock) (int mutex_handle);

int (*__nacl_irt_cond_create) (int *cond_handle);
int (*__nacl_irt_cond_destroy) (int cond_handle);
int (*__nacl_irt_cond_signal) (int cond_handle);
int (*__nacl_irt_cond_broadcast) (int cond_handle);
int (*__nacl_irt_cond_wait) (int cond_handle, int mutex_handle);
int (*__nacl_irt_cond_timed_wait_abs) (int cond_handle, int mutex_handle,
                                       // ARC MOD BEGIN UPSTREAM nacl-use-abi-timespec
                                       const struct nacl_abi_timespec *abstime);
                                       // ARC MOD END UPSTREAM

int (*__nacl_irt_tls_init) (void *tdb);
void *(*__nacl_irt_tls_get) (void);

int (*__nacl_irt_open_resource) (const char* file, int *fd);

// ARC MOD BEGIN UPSTREAM nacl-use-abi-timespec
// Use nacl_abi_timespec.
int (*__nacl_irt_clock_getres) (nacl_irt_clockid_t clk_id,
                                struct nacl_abi_timespec *res);
int (*__nacl_irt_clock_gettime) (nacl_irt_clockid_t clk_id,
                                 struct nacl_abi_timespec *tp);
// ARC MOD END UPSTREAM

int (*__nacl_irt_getpid) (int *pid);

int (*__nacl_irt_unlink)(const char *pathname);
int (*__nacl_irt_truncate)(const char *pathname, off_t length);
int (*__nacl_irt_lstat) (const char *pathname, struct nacl_abi_stat *);
int (*__nacl_irt_link)(const char *oldpath, const char *newpath);
int (*__nacl_irt_rename)(const char *oldpath, const char *newpath);
int (*__nacl_irt_symlink)(const char *oldpath, const char *newpath);
int (*__nacl_irt_chmod)(const char *path, mode_t mode);
int (*__nacl_irt_access)(const char *path, int amode);
int (*__nacl_irt_readlink)(const char *path, char *buf,
                           size_t count, size_t *nread);
int (*__nacl_irt_utimes)(const char *filename,
                         const struct timeval *times);

int (*__nacl_irt_fchdir)(int fd);
int (*__nacl_irt_fchmod)(int fd, mode_t mode);
int (*__nacl_irt_fsync)(int fd);
int (*__nacl_irt_fdatasync)(int fd);
int (*__nacl_irt_ftruncate)(int fd, off_t length);

// ARC MOD BEGIN
// Add a function pointer for nacl_list_mappings.
int (*__nacl_irt_list_mappings) (struct NaClMemMappingInfo *regions,
                                 size_t count, size_t *result_count);
// Add functions for nacl_futex.
int (*__nacl_irt_futex_wait_abs) (volatile int *addr, int value,
                                  const struct nacl_abi_timespec *abstime);
int (*__nacl_irt_futex_wake) (volatile int *addr, int nwake, int *count);
// ARC MOD END
// ARC MOD BEGIN
// Add __nacl_irt_write_real.
__LIBC_HIDDEN__
int (*__nacl_irt_write_real) (int fd, const void *buf, size_t count,
                              size_t *nwrote);
// Add __nacl_irt_clear_cache.
int (*__nacl_irt_clear_cache) (void *addr, size_t size);

// Add Bare Metal specific interfaces.
#if defined(BARE_METAL_BIONIC)
void (*__bare_metal_irt_notify_gdb_of_load)(struct link_map* map);
void (*__bare_metal_irt_notify_gdb_of_unload)(struct link_map* map);
void (*__bare_metal_irt_notify_gdb_of_libraries)(void);
#endif
// ARC MOD END

void
// ARC MOD BEGIN
// Renamed from init_irt_table to __init_irt_table.
__init_irt_table (void)
// ARC MOD END
{
  union {
    struct nacl_irt_basic nacl_irt_basic;
    struct nacl_irt_fdio nacl_irt_fdio;
    struct nacl_irt_filename nacl_irt_filename;
    // ARC MOD BEGIN
    // Use nacl_irt_memory instead of nacl_irt_memory_v0_2 if 0.3 is
    // available.
    struct nacl_irt_memory nacl_irt_memory;
    // As the first element (sysbrk) of nacl_irt_memory is removed in
    // v0.3, we should have different storage for v0.1 and v0.2.
    struct nacl_irt_memory_v0_2 nacl_irt_memory_v0_2;
    // ARC MOD END
    struct nacl_irt_dyncode nacl_irt_dyncode;
    struct nacl_irt_thread nacl_irt_thread;
    struct nacl_irt_mutex nacl_irt_mutex;
    struct nacl_irt_cond nacl_irt_cond;
    struct nacl_irt_tls nacl_irt_tls;
    struct nacl_irt_resource_open nacl_irt_resource_open;
    struct nacl_irt_clock nacl_irt_clock;
    struct nacl_irt_dev_getpid nacl_irt_dev_getpid;
    struct nacl_irt_dev_fdio nacl_irt_dev_fdio;
    struct nacl_irt_dev_filename_v0_2 nacl_irt_dev_filename_v0_2;
    struct nacl_irt_dev_filename nacl_irt_dev_filename;
    // ARC MOD BEGIN
    // Add some IRT interface structures.
    struct nacl_irt_futex nacl_irt_futex;
    struct nacl_irt_dev_list_mappings nacl_irt_list_mappings;
    struct nacl_irt_icache nacl_irt_icache;
#if defined(BARE_METAL_BIONIC)
    struct bare_metal_irt_debugger bare_metal_irt_debugger;
#endif
    // ARC MOD END
  } u;

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_BASIC_v0_1, &u.nacl_irt_basic,
                        sizeof(u.nacl_irt_basic)) == sizeof(u.nacl_irt_basic))
    {
      __nacl_irt_exit = u.nacl_irt_basic.exit;
      __nacl_irt_gettod = u.nacl_irt_basic.gettod;
      __nacl_irt_clock = u.nacl_irt_basic.clock;
      __nacl_irt_nanosleep = u.nacl_irt_basic.nanosleep;
      __nacl_irt_sched_yield = u.nacl_irt_basic.sched_yield;
      __nacl_irt_sysconf = u.nacl_irt_basic.sysconf;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END
  // ARC MOD BEGIN
  // TODO(crbug.com/242349): Getting NACL_IRT_DEV_FDIO_v0_2 always fails at
  // this point. Need to fix native_client/src/untrusted/irt/irt_interfaces.c.
  // ARC MOD END
  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_FDIO_v0_1, &u.nacl_irt_fdio,
                        sizeof(u.nacl_irt_fdio)) == sizeof(u.nacl_irt_fdio))
    {
      __nacl_irt_close = u.nacl_irt_fdio.close;
      __nacl_irt_dup = u.nacl_irt_fdio.dup;
      __nacl_irt_dup2 = u.nacl_irt_fdio.dup2;
      __nacl_irt_read = u.nacl_irt_fdio.read;
      __nacl_irt_write = u.nacl_irt_fdio.write;
      __nacl_irt_seek = u.nacl_irt_fdio.seek;
      __nacl_irt_fstat = u.nacl_irt_fdio.fstat;
      __nacl_irt_getdents = u.nacl_irt_fdio.getdents;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END
  // ARC MOD BEGIN
  // For Bare Metal's debugger support. See crbug.com/354290
  __nacl_irt_open = not_implemented_open;
#ifdef BARE_METAL_BIONIC
  // TODO(crbug.com/354290): Remove this code.
  __nacl_irt_open_real = not_implemented_open;
#endif
  // ARC MOD END
  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_FILENAME_v0_1, &u.nacl_irt_filename,
                        sizeof(u.nacl_irt_filename)) ==
      sizeof(u.nacl_irt_filename))
    {
      __nacl_irt_open = u.nacl_irt_filename.open;
      // ARC MOD BEGIN
      // For Bare Metal's debugger support. See crbug.com/354290
#ifdef BARE_METAL_BIONIC
      // TODO(crbug.com/354290): Remove this code.
      __nacl_irt_open_real = u.nacl_irt_filename.open;
#endif
      // Upstream uses nacl_abi_stat as it #define stat.
      // __nacl_irt_stat = u.nacl_irt_filename.nacl_abi_stat;
      __nacl_irt_stat = u.nacl_irt_filename.stat;
    }
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END
  // ARC MOD BEGIN
  // Do not fill __nacl_irt_sysbrk and use NACL_IRT_MEMORY_v0_3.
  __nacl_irt_sysbrk = not_implemented;
  if (__nacl_irt_query &&
      __nacl_irt_query(NACL_IRT_MEMORY_v0_3, &u.nacl_irt_memory,
                       sizeof(u.nacl_irt_memory)) ==
      sizeof(u.nacl_irt_memory)) {
    __nacl_irt_mmap = u.nacl_irt_memory.mmap;
    __nacl_irt_munmap = u.nacl_irt_memory.munmap;
    __nacl_irt_mprotect = u.nacl_irt_memory.mprotect;
  }
  // Remove the fallback to direct NaCl syscalls and old IRT handling.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_DYNCODE_v0_1, &u.nacl_irt_dyncode,
                        sizeof(u.nacl_irt_dyncode)) ==
      sizeof(u.nacl_irt_dyncode))
    {
      __nacl_irt_dyncode_create = u.nacl_irt_dyncode.dyncode_create;
      __nacl_irt_dyncode_modify = u.nacl_irt_dyncode.dyncode_modify;
      __nacl_irt_dyncode_delete = u.nacl_irt_dyncode.dyncode_delete;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_THREAD_v0_1, &u.nacl_irt_thread,
                        sizeof(u.nacl_irt_thread)) ==
      sizeof(u.nacl_irt_thread))
    {
      __nacl_irt_thread_create = u.nacl_irt_thread.thread_create;
      __nacl_irt_thread_exit = u.nacl_irt_thread.thread_exit;
      __nacl_irt_thread_nice = u.nacl_irt_thread.thread_nice;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END
  // ARC MOD BEGIN
  // Remove deprecated NACL_IRT_MUTEX and NACL_IRT_COND.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_TLS_v0_1, &u.nacl_irt_tls,
                        sizeof(u.nacl_irt_tls)) == sizeof(u.nacl_irt_tls))
    {
      __nacl_irt_tls_init = u.nacl_irt_tls.tls_init;
      __nacl_irt_tls_get = u.nacl_irt_tls.tls_get;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_RESOURCE_OPEN_v0_1, &u.nacl_irt_resource_open,
                        sizeof(u.nacl_irt_resource_open)) ==
      sizeof(u.nacl_irt_resource_open))
    {
      ___nacl_irt_open_resource = u.nacl_irt_resource_open.open_resource;
      __nacl_irt_open_resource = nacl_irt_open_resource;
#ifdef IS_IN_rtld
      if (_dl_argc == 1)
        {
          static const char *argv[] =
        {
            DL_DST_LIB "/runnable-ld.so",
            DL_DST_LIB "/main.nexe",
            0
        };
          _dl_argc = 2;
          _dl_argv = (char **)argv;
        }
#endif
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_CLOCK_v0_1, &u.nacl_irt_clock,
                        sizeof(u.nacl_irt_clock)) == sizeof(u.nacl_irt_clock))
    {
      __nacl_irt_clock_getres = u.nacl_irt_clock.clock_getres;
      __nacl_irt_clock_gettime = u.nacl_irt_clock.clock_gettime;
    }
  // ARC MOD BEGIN
  // Remove the fallback to direct NaCl syscalls.
  // ARC MOD END

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_DEV_GETPID_v0_1, &u.nacl_irt_dev_getpid,
                        sizeof(u.nacl_irt_dev_getpid)) ==
      sizeof(u.nacl_irt_dev_getpid))
    {
      __nacl_irt_getpid = u.nacl_irt_dev_getpid.getpid;
    }
  else
    {
      __nacl_irt_getpid = not_implemented;
    }
  // ARC MOD BEGIN
  // TODO(crbug.com/242349): Getting NACL_IRT_DEV_FDIO_v0_2 always
  // fails at this point. For SFI NaCl, we should be able to use v0_3
  // interface, but this is not ready in non-SFI mode.
  // ARC MOD END
  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_DEV_FDIO_v0_2, &u.nacl_irt_dev_fdio,
                        sizeof(u.nacl_irt_dev_fdio)) ==
      sizeof(u.nacl_irt_dev_fdio))
    {
      __nacl_irt_fchdir = u.nacl_irt_dev_fdio.fchdir;
      __nacl_irt_fchmod = u.nacl_irt_dev_fdio.fchmod;
      __nacl_irt_fsync = u.nacl_irt_dev_fdio.fsync;
      __nacl_irt_fdatasync = u.nacl_irt_dev_fdio.fdatasync;
      __nacl_irt_ftruncate = u.nacl_irt_dev_fdio.ftruncate;
    }
  else
    {
      __nacl_irt_fchdir = not_implemented;
      // ARC MOD BEGIN
      // Add a cast. We need this because mode_t is a short and GCC
      // thinks this is incompatible with variable args.
      __nacl_irt_fchmod = (int (*)(int, mode_t))not_implemented;
      // ARC MOD END
      __nacl_irt_fsync = not_implemented;
      __nacl_irt_fdatasync = not_implemented;
      __nacl_irt_ftruncate = not_implemented;
    }

  if (__nacl_irt_query &&
      __nacl_irt_query (NACL_IRT_DEV_FILENAME_v0_3, &u.nacl_irt_dev_filename,
                        sizeof(u.nacl_irt_dev_filename)) ==
      sizeof(u.nacl_irt_dev_filename))
    {
      __nacl_irt_mkdir = u.nacl_irt_dev_filename.mkdir;
      __nacl_irt_chdir = u.nacl_irt_dev_filename.chdir;
      __nacl_irt_rmdir = u.nacl_irt_dev_filename.rmdir;
      __nacl_irt_getcwd = u.nacl_irt_dev_filename.getcwd;
      __nacl_irt_unlink = u.nacl_irt_dev_filename.unlink;
      __nacl_irt_truncate = u.nacl_irt_dev_filename.truncate;
      __nacl_irt_lstat = u.nacl_irt_dev_filename.lstat;
      __nacl_irt_link = u.nacl_irt_dev_filename.link;
      __nacl_irt_rename = u.nacl_irt_dev_filename.rename;
      __nacl_irt_symlink = u.nacl_irt_dev_filename.symlink;
      __nacl_irt_chmod = u.nacl_irt_dev_filename.chmod;
      __nacl_irt_access = u.nacl_irt_dev_filename.access;
      __nacl_irt_readlink = u.nacl_irt_dev_filename.readlink;
      __nacl_irt_utimes = u.nacl_irt_dev_filename.utimes;
    }
  else if (__nacl_irt_query &&
           __nacl_irt_query (NACL_IRT_DEV_FILENAME_v0_2,
                             &u.nacl_irt_dev_filename_v0_2,
                             sizeof(u.nacl_irt_dev_filename_v0_2)) ==
           sizeof(u.nacl_irt_dev_filename_v0_2))
    {
      __nacl_irt_mkdir = u.nacl_irt_dev_filename_v0_2.mkdir;
      __nacl_irt_chdir = u.nacl_irt_dev_filename_v0_2.chdir;
      __nacl_irt_rmdir = u.nacl_irt_dev_filename_v0_2.rmdir;
      __nacl_irt_getcwd = u.nacl_irt_dev_filename_v0_2.getcwd;
      __nacl_irt_unlink = u.nacl_irt_dev_filename_v0_2.unlink;
      __nacl_irt_truncate = not_implemented;
      __nacl_irt_lstat = not_implemented;
      __nacl_irt_link = not_implemented;
      __nacl_irt_rename = not_implemented;
      __nacl_irt_symlink = not_implemented;
      // ARC MOD BEGIN
      // Add a cast. We need this because mode_t is a short and GCC
      // thinks this is incompatible with variable args.
      __nacl_irt_chmod = (int (*)(const char *, mode_t))not_implemented;
      // ARC MOD END
      __nacl_irt_access = not_implemented;
      __nacl_irt_readlink = not_implemented;
      __nacl_irt_utimes = not_implemented;
    }
  else
    {
      // ARC MOD BEGIN
      // Add a cast. We need this because mode_t is a short and GCC
      // thinks this is incompatible with variable args.
      __nacl_irt_mkdir = (int (*)(const char *, mode_t))not_implemented;
      // ARC MOD END
      __nacl_irt_chdir = not_implemented;
      __nacl_irt_rmdir = not_implemented;
      __nacl_irt_getcwd = not_implemented;
      __nacl_irt_unlink = not_implemented;
      __nacl_irt_truncate = not_implemented;
      __nacl_irt_lstat = not_implemented;
      __nacl_irt_link = not_implemented;
      __nacl_irt_rename = not_implemented;
      __nacl_irt_symlink = not_implemented;
      // ARC MOD BEGIN
      // Add a cast. We need this because mode_t is a short and GCC
      // thinks this is incompatible with variable args.
      __nacl_irt_chmod = (int (*)(const char *, mode_t))not_implemented;
      // ARC MOD END
      __nacl_irt_access = not_implemented;
      __nacl_irt_readlink = not_implemented;
      __nacl_irt_utimes = not_implemented;
    }
  // ARC MOD BEGIN
  // Get __nacl_irt_list_mappings.
  if (__nacl_irt_query &&
      __nacl_irt_query(NACL_IRT_DEV_LIST_MAPPINGS_v0_1,
                       &u.nacl_irt_list_mappings,
                       sizeof(u.nacl_irt_list_mappings)) ==
      sizeof(u.nacl_irt_list_mappings)) {
    __nacl_irt_list_mappings = u.nacl_irt_list_mappings.list_mappings;
  }
  // Get futex functions.
  if (__nacl_irt_query &&
      __nacl_irt_query(NACL_IRT_FUTEX_v0_1,
                       &u.nacl_irt_futex,
                       sizeof(u.nacl_irt_futex)) ==
      sizeof(u.nacl_irt_futex)) {
    __nacl_irt_futex_wait_abs = u.nacl_irt_futex.futex_wait_abs;
    __nacl_irt_futex_wake = u.nacl_irt_futex.futex_wake;
  }
  // Get __nacl_irt_clear_cache.
  // __nacl_irt_clear_cache is supported only for Non-SFI NaCl on ARM.
  __nacl_irt_clear_cache = not_implemented;
  if (__nacl_irt_query &&
      __nacl_irt_query(NACL_IRT_ICACHE_v0_1,
                       &u.nacl_irt_icache,
                       sizeof(u.nacl_irt_icache)) ==
      sizeof(u.nacl_irt_icache)) {
    __nacl_irt_clear_cache = u.nacl_irt_icache.clear_cache;
  }
  // ARC MOD END
  // ARC MOD BEGIN
  // Add Bare Metal specific interfaces.
#if defined(BARE_METAL_BIONIC)
  if (__nacl_irt_query &&
      __nacl_irt_query(BARE_METAL_IRT_DEBUGGER_v0_1,
                       &u.bare_metal_irt_debugger,
                       sizeof(u.bare_metal_irt_debugger)) ==
      sizeof(u.bare_metal_irt_debugger)) {
    __bare_metal_irt_notify_gdb_of_load =
        u.bare_metal_irt_debugger.notify_gdb_of_load;
    __bare_metal_irt_notify_gdb_of_unload =
        u.bare_metal_irt_debugger.notify_gdb_of_unload;
    __bare_metal_irt_notify_gdb_of_libraries =
        u.bare_metal_irt_debugger.notify_gdb_of_libraries;
  }
#endif
  // ARC MOD END

  __nacl_irt_epoll_create = not_implemented;
  __nacl_irt_epoll_create1 = not_implemented;
  __nacl_irt_epoll_ctl = not_implemented;
  __nacl_irt_epoll_pwait = not_implemented;
  __nacl_irt_epoll_wait = not_implemented;
  __nacl_irt_poll = not_implemented;
  __nacl_irt_ppoll = not_implemented;
  __nacl_irt_socket = not_implemented;
  __nacl_irt_accept = not_implemented;
  __nacl_irt_bind = not_implemented;
  __nacl_irt_listen = not_implemented;
  __nacl_irt_connect = not_implemented;
  __nacl_irt_send = not_implemented;
  __nacl_irt_sendmsg = not_implemented;
  __nacl_irt_sendto = not_implemented;
  __nacl_irt_recv = not_implemented;
  __nacl_irt_recvmsg = not_implemented;
  __nacl_irt_recvfrom = not_implemented;
  __nacl_irt_select = not_implemented;
  __nacl_irt_pselect = not_implemented;
  __nacl_irt_getpeername = not_implemented;
  __nacl_irt_getsockname = not_implemented;
  __nacl_irt_getsockopt = not_implemented;
  __nacl_irt_setsockopt = not_implemented;
  __nacl_irt_socketpair = not_implemented;
  __nacl_irt_shutdown = not_implemented;
  // ARC MOD BEGIN
  // Initialize __nacl_irt_write_real.
  __nacl_irt_write_real = __nacl_irt_write;
  // ARC MOD END
}

size_t nacl_interface_query(const char *interface_ident,
                            void *table, size_t tablesize) {
  return (*__nacl_irt_query)(interface_ident, table, tablesize);
}
// ARC MOD BEGIN
// Note that this function or __init_irt_table() must be called from
// both the loader and main program because the addresses of their
// __nacl_irt_* are different.
void __init_irt_from_irt_query(__nacl_irt_query_fn_t irt_query) {
#ifdef BARE_METAL_BIONIC
  // TODO(crbug.com/354290): Remove this code.
  ___nacl_irt_query = irt_query;
  __nacl_irt_query = nacl_irt_query;
#else
  __nacl_irt_query = irt_query;
#endif
  // We will just crash in __init_irt_table due to NULL pointer access
  // if we could not find __nacl_irt_query. This should not happen.
  __init_irt_table();
}
// ARC MOD END
