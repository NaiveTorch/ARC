// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/nacl_dyncode_create.c"

#include <errno.h>

// ARC MOD BEGIN
// Include nacl/nacl_dyncode.h instead of nacl_dyncode.h.
#include <nacl/nacl_dyncode.h>
// ARC MOD END
#include <irt_syscalls.h>


int __nacl_dyncode_create (void *dest, const void *src, size_t size)
{
  int retval = __nacl_irt_dyncode_create (dest, src, size);
  if (retval > 0) {
    errno = retval;
    return -1;
  }
  // ARC MOD BEGIN UPSTREAM treat-zero-and-neg-zero-the-same
  // Prefer 0 to -retval.
  return 0;
  // ARC MOD END UPSTREAM
}
libc_hidden_def (__nacl_dyncode_create)
// ARC MOD BEGIN
// Expose nacl_dyncode_create from libc.so.
weak_alias(__nacl_dyncode_create, nacl_dyncode_create)
// ARC MOD END
