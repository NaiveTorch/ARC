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

#include "libc_init_common.h"

#include <asm/page.h>
#include <bionic_tls.h>
#include <elf.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/auxv.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <unistd.h>

#include "atexit.h"
#include "private/bionic_auxv.h"
#include "private/bionic_ssp.h"
#include "private/KernelArgumentBlock.h"
#include "pthread_internal.h"
// ARC MOD BEGIN
// Include irt.h and irt_syscalls.h to use random for __stack_chk_guard.
#if defined(BARE_METAL_BIONIC)
#include <irt.h>
#include <irt_syscalls.h>
#include <sys/endian.h>
#endif
// ARC MOD END

extern "C" abort_msg_t** __abort_message_ptr;
extern "C" unsigned __get_sp(void);
extern "C" int __system_properties_init(void);

// Not public, but well-known in the BSDs.
const char* __progname;

// Declared in <unistd.h>.
char** environ;

// Declared in <private/bionic_ssp.h>.
uintptr_t __stack_chk_guard = 0;

// Declared in <asm/page.h>.
unsigned int __page_size = PAGE_SIZE;
unsigned int __page_shift = PAGE_SHIFT;

static size_t get_stack_size() {
  const size_t minimal_stack_size = 128 * 1024;
  size_t stack_size = minimal_stack_size;
  // ARC MOD BEGIN
  // TLS has not been initialized yet, so calling getrlimit, which
  // updates errno is invalid on both NaCl and Bare Metal.
#if !defined(__native_client__) && !defined(BARE_METAL_BIONIC)
  // ARC MOD END
  struct rlimit stack_limit;
  int rlimit_result = getrlimit(RLIMIT_STACK, &stack_limit);
  if ((rlimit_result == 0) && (stack_limit.rlim_cur != RLIM_INFINITY)) {
    stack_size = stack_limit.rlim_cur;
    stack_size = (stack_size & ~(PAGE_SIZE - 1));
    if (stack_size < minimal_stack_size) {
      stack_size = minimal_stack_size;
    }
  }
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  return stack_size;
}

/* Init TLS for the initial thread. Called by the linker _before_ libc is mapped
 * in memory. Beware: all writes to libc globals from this function will
 * apply to linker-private copies and will not be visible from libc later on.
 *
 * Note: this function creates a pthread_internal_t for the initial thread and
 * stores the pointer in TLS, but does not add it to pthread's gThreadList. This
 * has to be done later from libc itself (see __libc_init_common).
 *
 * This function also stores a pointer to the kernel argument block in a TLS slot to be
 * picked up by the libc constructor.
 */
void __libc_init_tls(KernelArgumentBlock& args) {
  __libc_auxv = args.auxv;

  uintptr_t stack_top = (__get_sp() & ~(PAGE_SIZE - 1)) + PAGE_SIZE;
  size_t stack_size = get_stack_size();
  uintptr_t stack_bottom = stack_top - stack_size;

  static void* tls[BIONIC_TLS_SLOTS];
  static pthread_internal_t thread;
  thread.tid = gettid();
  thread.tls = tls;
  pthread_attr_init(&thread.attr);
  pthread_attr_setstack(&thread.attr, (void*) stack_bottom, stack_size);
  _init_thread(&thread, false);
  __init_tls(&thread);
  tls[TLS_SLOT_BIONIC_PREINIT] = &args;
}

// ARC MOD BEGIN
#if defined(BARE_METAL_BIONIC)
// Define helper functions to initialize __stack_chk_guard for ARC.
static void init_stack_chk_guard_by_irt_random() {
  nacl_irt_random irt_random;
  if (__nacl_irt_query(NACL_IRT_RANDOM_v0_1, &irt_random,
                       sizeof(irt_random)) != sizeof(irt_random)) {
    static const char msg[] =
        "Failed to get irt_random for __stack_chk_guard! "
        "(this is OK for unittests)\n";
    write(STDERR_FILENO, msg, sizeof(msg) - 1);
  }
  size_t nread;
  if (irt_random.get_random_bytes(
          reinterpret_cast<char*>(&__stack_chk_guard),
          sizeof(__stack_chk_guard), &nread) != 0 ||
      nread != sizeof(__stack_chk_guard)) {
    static const char msg[] =
        "Failed to get random bytes for __stack_chk_guard!\n";
    write(STDERR_FILENO, msg, sizeof(msg) - 1);
    exit(1);
  }
}
#endif

static void init_stack_chk_guard() {
  // __stack_chk_guard is a variable which could be used by GCC to detect stack
  // smashing (see -fstack-protector).
  //
  // Since NaCl does not provide AT_RANDOM, we fill a fixed value
  // here. This would be okay for NaCl because NaCl toolchain does not
  // support -fstack-protector anyway.
  __stack_chk_guard = 0xfee1dead;
#if defined(BARE_METAL_BIONIC)
  // For Bare Metal mode, we use IRT random to initialize the
  // canary. If IRT random does not exist, it means we are using
  // nonsfi_loader which does not have IRT random and we are running a
  // unittest. We do not care the security of unittests, let's just
  // keep going.
  init_stack_chk_guard_by_irt_random();
#elif !defined(__native_client__)
#error Either __native_client__ or BARE_METAL_BIONIC must be set.
#endif
}
// ARC MOD END
void __libc_init_common(KernelArgumentBlock& args) {
  // Initialize various globals.
  environ = args.envp;
  errno = 0;
  __libc_auxv = args.auxv;
  __progname = args.argv[0] ? args.argv[0] : "<unknown>";
  __abort_message_ptr = args.abort_message_ptr;

  // AT_RANDOM is a pointer to 16 bytes of randomness on the stack.
  // ARC MOD BEGIN
#if defined(HAVE_ARC)
  init_stack_chk_guard();
  // The least significant byte of the canary must be zero to prevent
  // memory exposure by functions like puts. This is compatible with
  // glibc. See
  // https://sourceware.org/git/?p=glibc.git;a=blob;f=sysdeps/generic/dl-osinfo.h;h=d7667f862dd40a2c2b4d4672cdef7a617f047274;hb=HEAD
#if BYTE_ORDER != LITTLE_ENDIAN
#error "We only support little endian architectures"
#endif
  __stack_chk_guard &= ~0xff;
#else
  // ARC MOD END
  __stack_chk_guard = *reinterpret_cast<uintptr_t*>(getauxval(AT_RANDOM));
  // ARC MOD BEGIN
#endif  // HAVE_ARC
  // ARC MOD END

  // Get the main thread from TLS and add it to the thread list.
  pthread_internal_t* main_thread = __get_thread();
  main_thread->allocated_on_heap = false;
  _pthread_internal_add(main_thread);

  __system_properties_init(); // Requires 'environ'.
}

/* This function will be called during normal program termination
 * to run the destructors that are listed in the .fini_array section
 * of the executable, if any.
 *
 * 'fini_array' points to a list of function addresses. The first
 * entry in the list has value -1, the last one has value 0.
 */
void __libc_fini(void* array) {
  void** fini_array = reinterpret_cast<void**>(array);
  const size_t minus1 = ~(size_t)0; /* ensure proper sign extension */

  /* Sanity check - first entry must be -1 */
  if (array == NULL || (size_t)fini_array[0] != minus1) {
    return;
  }

  /* skip over it */
  fini_array += 1;

  /* Count the number of destructors. */
  int count = 0;
  while (fini_array[count] != NULL) {
    ++count;
  }

  /* Now call each destructor in reverse order. */
  while (count > 0) {
    void (*func)() = (void (*)()) fini_array[--count];

    /* Sanity check, any -1 in the list is ignored */
    if ((size_t)func == minus1) {
      continue;
    }

    func();
  }

#ifndef LIBC_STATIC
  {
    extern void __libc_postfini(void) __attribute__((weak));
    if (__libc_postfini) {
      __libc_postfini();
    }
  }
#endif
}
