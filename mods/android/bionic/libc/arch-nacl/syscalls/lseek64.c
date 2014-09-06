// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/llseek.c"

#include <errno.h>

#include <irt_syscalls.h>


loff_t __llseek (int fd, loff_t offset, int whence)
{
  int result = __nacl_irt_seek (fd, offset, whence, &offset);
  if (result != 0)
    {
      errno = result;
      return -1;
    }
  return offset;
}
// ARC MOD BEGIN
// Define lseek64 instead of llseek as we do not have the wrapper.
weak_alias (__llseek, lseek64)
// ARC MOD END
