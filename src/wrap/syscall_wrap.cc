/* Copyright 2014 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Linux syscall wrapper.
 * Both platforms expect definitions provided by <sys/syscall.h> of Bionic.
 * Note that NaCl x86-64 also uses one for i686 as Bionic does not have
 * sys/syscall.h for x86-64.
 */

#include <errno.h>
#include <stdarg.h>
#include <sys/syscall.h>
#include <sys/types.h>

#include "base/basictypes.h"
#include "common/arc_strace.h"

namespace {

int HandleSyscallGettid() {
  ARC_STRACE_ENTER("syscall", "%s", "__NR_gettid");
  const int result = gettid();
  ARC_STRACE_RETURN(result);
}

int HandleSyscallDefault(int number) {
  // TODO(crbug.com/241955): Stringify |number|.
  ARC_STRACE_ENTER("syscall", "%d, ...", number);
  errno = ENOSYS;
  ARC_STRACE_RETURN(-1);
}

}  // namespace

extern "C" int __wrap_syscall(int number, ...) {
  // Defining a function with variable argument without using va_start/va_end
  // is not portable and may cause crash.
  va_list ap;
  va_start(ap, number);
  int result;

  // The number is based on not running Android platform, but ARC build
  // target platform. NDK should not pass directly the number applications use.
  switch (number) {
    case __NR_gettid:
      result = HandleSyscallGettid();
      break;
    default:
      result = HandleSyscallDefault(number);
      break;
  }
  va_end(ap);
  return result;
}
