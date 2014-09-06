// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/xstat.c"

#include <errno.h>
#include <sys/stat.h>

#include <nacl_stat.h>
#include <irt_syscalls.h>

// ARC MOD BEGIN
// Define stat instead of __xstat
int stat(const char *path, struct stat *buf)
// ARC MOD END
{
  if (buf == NULL || path == NULL)
    {
      errno = EFAULT;
      return -1;
    }
  struct nacl_abi_stat st;
  int result = __nacl_irt_stat (path, &st);
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
// Remove xstat handling.
// ARC MOD END
