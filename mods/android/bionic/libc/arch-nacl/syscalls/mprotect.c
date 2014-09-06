// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/mprotect.c"

#include <errno.h>
#include <sys/mman.h>

#include <irt_syscalls.h>

// ARC MOD BEGIN
// |addr| is const in bionic.
int __mprotect (const void *addr, size_t len, int prot)
// ARC MOD END
{
  // ARC MOD BEGIN
  // Disallow mmap with both PROT_WRITE and PROT_EXEC so that we can
  // make sure only whitelisted code creates writable executable
  // pages. To create RWX pages, use arc::MprotectRWX explicitly.
  if ((prot & PROT_WRITE) && (prot & PROT_EXEC)) {
    errno = EPERM;
    return -1;
  }
  // ARC MOD END
  int result = __nacl_irt_mprotect (addr, len, prot);
  if (result != 0) {
    errno = result;
    return -1;
  }
  return 0;
}
weak_alias (__mprotect, mprotect)
