// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/mmap.c"

#include <sys/types.h>
#include <sys/mman.h>
#include <errno.h>

#include <irt_syscalls.h>


// ARC MOD BEGIN
// Return void* instead of __ptr_t and add code for debug logs.
void *__mmap(void *addr, size_t len, int prot, int flags,
           int fd, off_t offset) {
// ARC MOD END
  // ARC MOD BEGIN
  // Disallow mmap with both PROT_WRITE and PROT_EXEC so that we can
  // make sure only whitelisted code creates writable executable
  // pages. To create RWX pages, use arc::MprotectRWX explicitly.
  if ((prot & PROT_WRITE) && (prot & PROT_EXEC)) {
    errno = EPERM;
    return -1;
  }
  // ARC MOD END
  int result = __nacl_irt_mmap (&addr, len, prot, flags, fd, offset);
  if (result != 0) {
    errno = result;
    return MAP_FAILED;
  }
  return addr;
}
weak_alias (__mmap, mmap)
