// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/gettimeofday.c"

#include <errno.h>
#include <time.h>

#include <irt_syscalls.h>
// ARC MOD BEGIN
// Add include.
#include <nacl_timeval.h>
// ARC MOD END
int __gettimeofday (struct timeval *tv, struct timezone *tz)
{
  // ARC MOD BEGIN
  // Use nacl_abi_timeval instead of timeval.
  struct nacl_abi_timeval nacl_tv;
  int result = __nacl_irt_gettod(&nacl_tv);
  // ARC MOD END
  if (result != 0) {
    errno = result;
    return -1;
  }
  // ARC MOD BEGIN
  // Convert timeval.
  if (tv)
    __nacl_abi_timeval_to_timeval(&nacl_tv, tv);
  // ARC MOD END
  if (tz != NULL) {
    tz->tz_dsttime = 0;
    tz->tz_minuteswest = 0;
  }
  return -result;
}
INTDEF (__gettimeofday)
weak_alias (__gettimeofday, gettimeofday)
