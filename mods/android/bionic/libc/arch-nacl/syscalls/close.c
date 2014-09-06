// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/close.c"

#include <errno.h>
#include <unistd.h>

#include <irt_syscalls.h>


int __close (int fd)
{
  int result = __nacl_irt_close (fd);
  if (result != 0) {
    errno = result;
    return -1;
  }
  // ARC MOD BEGIN UPSTREAM treat-zero-and-neg-zero-the-same
  // Return 0 instead of -result.
  return 0;
  // ARC MOD END UPSTREAM
}
libc_hidden_def (__close)
weak_alias (__close, close)
strong_alias (__close, __libc_close)
strong_alias (__close, __close_nocancel)
