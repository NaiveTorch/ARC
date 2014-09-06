// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/nacl_read_tp.c"

#include <irt_syscalls.h>

#ifdef __x86_64__
void* __attribute__ ((const)) __nacl_read_tp ()
{
  return __nacl_irt_tls_get ();
}
#endif

#ifdef __x86_64__
/* NaCl imposes severe limitations on call instruction alignment. This implies
   we have to keep calls on the same position when doing TLS rewrites.
   Unfortunately, dynamic TLS models call __tls_get_addr at the end, while exec
   TLS models call __nacl_read_tp at the beginning.

   __nacl_add_tp returns thread pointer plus an offset passed in the first
   argument. Using __nacl_add_tp we can create exec TLS models code sequences
   with call at the end, thus enabling dynamic to exec TLS rewrites.

   For example, __nacl_read_tp initial exec code sequence is:
     call __nacl_read_tp
     add x@gottpoff(%rip),%eax

   And __nacl_add_tp equivalent is:
     mov x@gottpoff(%rip),%edi  #  first integer argument is passed in %rdi
     call __nacl_add_tp  */

void* __nacl_add_tp (ptrdiff_t off)
{
  return (char*) __nacl_irt_tls_get () + off;
}
#endif
// ARC MOD BEGIN
// Add __get_tls for bionic.
void* __get_tls(void)
{
#if defined(__arm__) && defined(__native_client__)
  void* tls;
  // r9 is the thread pointer on ARM. Note that the NaCl validator
  // allows programs to read the thread pointer with the following
  // form, while writing to r9 or [r9] is always prohibited.
  asm("ldr  %0, [%%r9]": "=r"(tls));
  return tls;
#else
  return __nacl_irt_tls_get();
#endif
}
// ARC MOD END
