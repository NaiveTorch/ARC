// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/nanosleep.c"

#include <errno.h>
#include <time.h>

#include <irt_syscalls.h>
// ARC MOD BEGIN
// Add include.
#include <nacl_timespec.h>
// ARC MOD END

int __nanosleep (const struct timespec *req, struct timespec *rem)
{
  // ARC MOD BEGIN
  // Convert timespecs.
  struct nacl_abi_timespec nacl_req;
  struct nacl_abi_timespec *nacl_req_ptr = NULL;
  struct nacl_abi_timespec nacl_rem;
  if (req) {
    __timespec_to_nacl_abi_timespec(req, &nacl_req);
    nacl_req_ptr = &nacl_req;
  }
  int result = __nacl_irt_nanosleep(nacl_req_ptr, &nacl_rem);
  // ARC MOD END
  if (result != 0) {
    errno = result;
    return -1;
  }
  // ARC MOD BEGIN
  // Convert |rem|.
  if (rem)
    __nacl_abi_timespec_to_timespec(&nacl_rem, rem);
  // ARC MOD END
  // ARC MOD BEGIN UPSTREAM treat-zero-and-neg-zero-the-same
  return 0;
  // ARC MOD END UPSTREAM
}
libc_hidden_def (__nanosleep)
weak_alias (__nanosleep, nanosleep)
