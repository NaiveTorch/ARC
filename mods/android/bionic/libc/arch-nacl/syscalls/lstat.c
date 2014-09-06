// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/lxstat.c"
#include <errno.h>
#include <sys/stat.h>

#include <irt_syscalls.h>

// ARC MOD BEGIN
// Define lstat instead of __lxstat
int lstat(const char *name, struct stat *buf)
// ARC MOD END
{
  if (buf == NULL || name == NULL)
    {
      errno = EFAULT;
      return -1;
    }
  struct nacl_abi_stat st;
  int result = __nacl_irt_lstat (name, &st);
  if (result != 0)
    {
      errno = result;
      return -1;
    }
  else
    {
      __nacl_abi_stat_to_stat (&st, buf);
      return 0;
    }
}
// ARC MOD BEGIN
// Remove lxstat handling.
// ARC MOD END
