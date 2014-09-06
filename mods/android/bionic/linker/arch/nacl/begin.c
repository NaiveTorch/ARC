// Copyright (C) 2014 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// The entry point of bionic's dynamic linker/loader on NaCl.
//

#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>

#include <irt_syscalls.h>
#include <private/at_sysinfo.h>

// See the comment in bionic/libc/arch-x86/bionic/stack_chk_fail_local.h
// and the equivalent include in bionic/libc/arch-x86/bionic/crtbegin_so.c
#if defined(__i386__) && defined(BARE_METAL_BIONIC)
#include "arch-x86/bionic/__stack_chk_fail_local.h"
#endif

// We define __linker_base whose address is the first address of the
// Bionic loader using --defsym flag for the linker. By declaring this
// with __LIBC_HIDDEN__, compiler generates code which does not depend
// on GOT. Specifically, it uses PC relative addressing so this symbol
// works before the self relocation. As neither NaCl nor Bare Metal
// service runtime send AT_BASE to the loader, we use this value instead.
__LIBC_HIDDEN__ extern unsigned __linker_base;

unsigned __linker_init(unsigned **elfdata);
void __init_irt_from_auxv(unsigned *auxv);
void __init_irt_from_irt_query(__nacl_irt_query_fn_t irt_query);

// Outputs message to stderr, and then exits with status code 1.
// Before invoking this function, IRT table must be initialized.
static void fail(const char* message, size_t message_length)
    __attribute__((noreturn));
static void fail(const char* message, size_t message_length) {
  static const int kStderrFd = 2;
  write(kStderrFd, message, message_length);
  exit(1);
}

void _start(unsigned **info) {
  int envc = (int)info[1];
  int argc = (int)info[2];
  char **argv = (char**)&info[3];
  char **envp = argv + argc + 1;
  unsigned *auxv = (unsigned *)(envp + envc + 1);
  int i, j;
  unsigned entry;
  unsigned **elfdata;
  __nacl_irt_query_fn_t irt_query = NULL;

  for (unsigned *auxv_iter = auxv; *auxv_iter != AT_NULL; auxv_iter += 2) {
    if (*auxv_iter == AT_SYSINFO)
      irt_query = (__nacl_irt_query_fn_t)auxv_iter[1];
  }
  __init_irt_from_irt_query(irt_query);

  /* As we will shift |argv| to remove the loader from it and we will
   * fill some auxv entries, we cannot reuse |info| so we will
   * allocate |elfdata| on stack of this function.
   *
   * Also note that we must share this data with both the loader and
   * the main program because the loader passes the pointer to this
   * region to the main program using TLS_SLOT_BIONIC_PREINIT.
   *
   * +--------------------------------------+ <- __nacl_linker_init and
   * | fini                                 |    entry point of main
   * +--------------------------------------+    program take this pointer.
   * | envc                                 |
   * +--------------------------------------+ <- __linker_init takes this.
   * | argc                                 |
   * +--------------------------------------+
   * |                                      |
   * .                                      |    We do not have the loader
   * . argv                                 | <- in argv (i.e., argv[0] is
   * .                                      |    the name of main program)
   * |                                      |
   * +--------------------------------------+
   * | NULL                                 |
   * +--------------------------------------+
   * |                                      |
   * .                                      |
   * . envp                                 |
   * .                                      |
   * |                                      |
   * +--------------------------------------+
   * | NULL                                 |
   * +--------------------------------------+
   * | AT_SYSINFO        auxv (12 elements) | ^
   * | __nacl_irt_query                     | |   Fields before here are
   * | AT_BASE                              | +-- filled by this function.
   * | The base address of the loader       |
   * | AT_PHDR                              | +-- __nacl_linker_init will
   * | Program header for main program      | |   fill auxv after AT_BASE.
   * | AT_PHNUM                             | v
   * | # of program headers in main program |
   * | AT_ENTRY                             |
   * | Entry address of main program        |
   * | AT_NULL                              |
   * | NULL                                 |
   * +--------------------------------------+
   */
  /* 3 for fini, envc, and argc. The number of argv will be decreased
   * by one because we do not pass the loader, and plus one for both
   * argv and envp for their NULL terminators. We will have 12
   * elements in auxv. */
  elfdata = (unsigned **)alloca((3 + argc - 1 + 1 + envc + 1 + 12) *
                                sizeof(unsigned *));
  j = 0;
  elfdata[j++] = (unsigned *)info[0];
  elfdata[j++] = (unsigned *)envc;
  if (argc < 0) {
    static const char kErrorMsg[] = "Negative argc";
    fail(kErrorMsg, sizeof(kErrorMsg) - 1);
  } else if (argc <= 1) {
    // When no argument is specified, load /lib/main.nexe. This is
    // compatible with nacl-glibc's runnable-ld.so. See
    // nacl-glibc/sysdeps/nacl/irt_syscalls.c.
    elfdata[j++] = (unsigned *)1;
    elfdata[j++] = (unsigned *)"/lib/main.nexe";
  } else {
    elfdata[j++] = (unsigned *)(argc - 1);
    for (i = 1; i < argc; i++)
      elfdata[j++] = (unsigned *)argv[i];
  }
  elfdata[j++] = NULL;
  for (i = 0; i < envc; i++)
    elfdata[j++] = (unsigned *)envp[i];
  elfdata[j++] = NULL;
  elfdata[j++] = (unsigned *)AT_SYSINFO;
  // We have not finished the self relocation yet. We cannot use
  // __nacl_irt_query here because it is a global variable and access
  // to global variables causes crash until the self relocation is
  // done. We should use irt_query, which is a local variable, instead.
  elfdata[j++] = (unsigned *)irt_query;
  elfdata[j++] = (unsigned *)AT_BASE;
  elfdata[j++] = &__linker_base;
  /* This field will be updated in __nacl_linker_init in
   * bionic/linker/linker.cpp. */

  elfdata[j++] = (unsigned *)AT_NULL;
  elfdata[j] = NULL;

  entry = __linker_init(&elfdata[2]);

  if (!elfdata[j]) {
    static const char kErrorMsg[] = "__nacl_linker_init did not update auxv";
    fail(kErrorMsg, sizeof(kErrorMsg) - 1);
  }

  ((void (*)(unsigned **))entry)(elfdata);
}
