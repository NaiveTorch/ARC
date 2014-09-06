// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/fxstat.c"

#include <errno.h>
#include <stddef.h>
#include <sys/stat.h>

// ARC MOD BEGIN
// Remove unnecessary include.
// ARC MOD END
#include <nacl_stat.h>
#include <irt_syscalls.h>

// ARC MOD BEGIN
// Remove __nacl_abi_stat_to_stat. We define it in nacl_stat.c
// ARC MOD END

// ARC MOD BEGIN
// Define fstat instead of __fxstat
int fstat(int fd, struct stat *buf)
// ARC MOD END
{
  if (buf == NULL) {
    errno = EFAULT;
    return -1;
  }
  struct nacl_abi_stat nacl_buf;
  int result = __nacl_irt_fstat (fd, &nacl_buf);
  if (result != 0) {
    errno = result;
    return -1;
  }
  __nacl_abi_stat_to_stat (&nacl_buf, buf);
  // ARC MOD BEGIN UPSTREAM treat-zero-and-neg-zero-the-same
  // Return 0 instead of -result.
  return 0;
  // ARC MOD END UPSTREAM
}
// ARC MOD BEGIN
// Remove fxstat handling.
// ARC MOD END
