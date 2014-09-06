/*
 * Copyright (C) 2012 The Android Open Source Project
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

#include "../../bionic/libc_init_common.h"
#include <stddef.h>
#include <stdint.h>

__attribute__ ((section (".preinit_array")))
void (*__PREINIT_ARRAY__)(void) = (void (*)(void)) -1;

__attribute__ ((section (".init_array")))
void (*__INIT_ARRAY__)(void) = (void (*)(void)) -1;

// ARC MOD BEGIN
// Bionic expects .fini_array starts with -1 just like .dtors, but
// glibc does not have the leading -1. So, GNU ld does not have
// special treatment for crtbegin.o in its linker script and we need
// to give the maximum priority for the first element.
//
// Upstream Android's linker script can place .fini_array in crtbegin
// at the beginning of the .fini_array section, so there is a no
// problem on Android.
//
// Note that .init_array works without the suffix because the Bionic
// loader uses DT_INIT_ARRAYSZ to see the size of .init_array, instead
// of relying on the -1 as a terminator. However, in Bionic,
// .fini_array in the main binary is processed by atexit() and
// atexit() uses -1 as the terminator of .fini_array. So, to run all
// global destructors properly, we need to give the first priority for
// .fini_array.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
__attribute__ ((section (".fini_array.00000")))
#else
__attribute__ ((section (".fini_array")))
#endif
// ARC MOD END
void (*__FINI_ARRAY__)(void) = (void (*)(void)) -1;

// ARC MOD BEGIN
// Use an argument to pass |elfdata|, following NaCl's calling
// convention. See nacl-glibc/sysdeps/nacl/start.c.
__LIBC_HIDDEN__ void _start(unsigned **info) {
// ARC MOD END
  structors_array_t array;
  array.preinit_array = &__PREINIT_ARRAY__;
  array.init_array = &__INIT_ARRAY__;
  array.fini_array = &__FINI_ARRAY__;

  // ARC MOD BEGIN
  // Get |raw_args| from |info|.
  void* raw_args = &info[2];
  // ARC MOD END
  __libc_init(raw_args, NULL, &main, &array);
}

#include "__dso_handle.h"
#include "atexit.h"
