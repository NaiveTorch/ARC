/*
 * Copyright (C) 2008 The Android Open Source Project
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *  * Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *  * Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */
/*
 * libc_init_dynamic.c
 *
 * This source files provides two important functions for dynamic
 * executables:
 *
 * - a C runtime initializer (__libc_preinit), which is called by
 *   the dynamic linker when libc.so is loaded. This happens before
 *   any other initializer (e.g. static C++ constructors in other
 *   shared libraries the program depends on).
 *
 * - a program launch function (__libc_init), which is called after
 *   all dynamic linking has been performed. Technically, it is called
 *   from arch-$ARCH/bionic/crtbegin_dynamic.S which is itself called
 *   by the dynamic linker after all libraries have been loaded and
 *   initialized.
 */

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <elf.h>
#include "atexit.h"
#include "KernelArgumentBlock.h"
#include "libc_init_common.h"
#include <bionic_tls.h>

extern "C" {
  extern void pthread_debug_init(void);
  extern void malloc_debug_init(void);
  extern void malloc_debug_fini(void);
};

/* ARC MOD BEGIN */
/* We need them to initialize IRT table. */
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#include <private/irt_query_marker.h>
#include <private/nacl_syscalls.h>
extern "C" void __init_irt_table (void);
#endif

#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
/* See bionic/libc/private/irt_query_marker.h for detail. */
#if defined(__arm__)
/* We use 00100, which is less than 00101 for __libc_preinit. Note
 * that GCC emits .init_array.00101 for constructor(101), which is
 * specified for __libc_preinit and old GNU linker (binutils-2.22)
 * cannot compare 100 and 00101 correctly. */
__attribute__((section(".init_array.00100")))
#else
/* This is 65535 - 100. The priority for .ctors will be subtracted
 * from 65535. */
__attribute__((section(".ctors.65435"), used))
#endif
void* __next_func_needs_irt_query = NEXT_CTOR_FUNC_NEEDS_IRT_QUERY_MARKER;

/* This function must be called before other constructors in Bionic.
 * Note that android/bionic/libc/unistd/time.c actually has an
 * __attribute__((constructor)). Note that 101 is the highest
 * priority allowed for user programs. */
__attribute__((constructor(101)))
static void __libc_preinit(__nacl_irt_query_fn_t irt_query) {
#else
/* ARC MOD END */
// We flag the __libc_preinit function as a constructor to ensure
// that its address is listed in libc.so's .init_array section.
// This ensures that the function is called by the dynamic linker
// as soon as the shared library is loaded.
__attribute__((constructor)) static void __libc_preinit() {
  /* ARC MOD BEGIN */
#endif
  /* Initialize IRT table using __nacl_irt_query. */
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  __nacl_irt_query = irt_query;
  __init_irt_table();
#endif
  /* ARC MOD END */
  // Read the kernel argument block pointer from TLS.
  void* tls = const_cast<void*>(__get_tls());
  KernelArgumentBlock** args_slot = &reinterpret_cast<KernelArgumentBlock**>(tls)[TLS_SLOT_BIONIC_PREINIT];
  KernelArgumentBlock* args = *args_slot;

  // Clear the slot so no other initializer sees its value.
  // __libc_init_common() will change the TLS area so the old one won't be accessible anyway.
  *args_slot = NULL;

  __libc_init_common(*args);

  // Hooks for the debug malloc and pthread libraries to let them know that we're starting up.
  /* ARC MOD BEGIN */
  // We do not use the pthread debug feature.
  // pthread_debug_init();
  /* ARC MOD END */
  malloc_debug_init();
}

__LIBC_HIDDEN__ void __libc_postfini() {
  // A hook for the debug malloc library to let it know that we're shutting down.
  malloc_debug_fini();
}

// This function is called from the executable's _start entry point
// (see arch-$ARCH/bionic/crtbegin_dynamic.S), which is itself
// called by the dynamic linker after it has loaded all shared
// libraries the executable depends on.
//
// Note that the dynamic linker has also run all constructors in the
// executable at this point.
__noreturn void __libc_init(void* raw_args,
                            void (*onexit)(void),
                            int (*slingshot)(int, char**, char**),
                            structors_array_t const * const structors) {

  KernelArgumentBlock args(raw_args);

  // Several Linux ABIs don't pass the onexit pointer, and the ones that
  // do never use it.  Therefore, we ignore it.

  // The executable may have its own destructors listed in its .fini_array
  // so we need to ensure that these are called when the program exits
  // normally.
  if (structors->fini_array) {
    __cxa_atexit(__libc_fini,structors->fini_array,NULL);
  }

  exit(slingshot(args.argc, args.argv, args.envp));
}
