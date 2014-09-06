// ARC MOD BEGIN
// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/_exit.c"
// Removed unnecessary includes.
// ARC MOD END
#include <irt_syscalls.h>


void _exit (int status)
{
  __nacl_irt_exit (status);
  // ARC MOD BEGIN
  // Added ifdef for other CPUs.
  while (1) {
#if defined(__x86_64__) || defined(__i386__)
    __asm__("hlt");
#elif defined(__arm__) && defined(BARE_METAL_BIONIC)
    __asm__("bkpt 0");
#else
#error "Unsupported architecture"
#endif
  }
  // ARC MOD END
}
libc_hidden_def (_exit)
weak_alias (_exit, _Exit)
