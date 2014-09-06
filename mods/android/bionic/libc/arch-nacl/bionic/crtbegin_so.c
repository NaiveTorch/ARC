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
// Defines the first element of ctors and dtors sections. All shared
// objects and executables should link this as the first object.
//
// Note: GCC 4.7 uses .init_array and .fini_array instead of .init,
// .fini, .ctors, and .dtors. Android is using GCC 4.7 and ARM NaCl uses
// GCC 4.8, so non-ARM part of this file does not correspond to other ports.
//

#include <private/irt_query_marker.h>
#include <private/nacl_syscalls.h>
#include <stdlib.h>

// See the comment in bionic/libc/arch-x86/bionic/stack_chk_fail_local.h
// and the equivalent include in bionic/libc/arch-x86/bionic/crtbegin_so.c
#if defined(__i386__) && defined(BARE_METAL_BIONIC)
#include "arch-x86/bionic/__stack_chk_fail_local.h"
#endif

extern int __cxa_atexit(void (*func)(void *), void *arg, void *dso);
extern void __cxa_finalize(void *);

extern void *__dso_handle;
typedef void (*structor_fn)(void);

// The first entries of the global constructors/destructors. Note that
// we skip the first element, so we set invalid values for them. It
// seems the first elements of these lists are -1 and they are usually
// terminated by 0. Though we could find no standard which enforces
// this, we follow the custom.
//
// Note that we cannot define them as arrays which have a single
// element. If we define them as something like
//
// const structor_fn __CTOR_LIST__[1] = { (structor_fn)-1 };
//
// If specify the size of __CTOR_LIST__ and __DTOR_LIST__ as 1, a
// smart compiler may find the behavior of *++iter in _fini and
// *--iter in _init are undefined because it will look like the code
// is using an invalid pointer, and they remove the while loop
// entirely. GCC 4.6.3-1ubuntu5 actually does this optimization.
__attribute__((section(".ctors"), visibility("hidden")))
const structor_fn __CTOR_LIST__ = (structor_fn)-1;
__attribute__((section(".dtors"), visibility("hidden")))
const structor_fn __DTOR_LIST__ = (structor_fn)-1;

// Unlike .ctors and .dtors, .eh_frame does not have a watchdog for
// the first element.
__attribute__((section (".eh_frame")))
const int __EH_FRAME_BEGIN__[0] = {};

void __register_frame_info(const void* eh, void* obj);
void __deregister_frame_info(const void* eh);

// The _fini function could be called in two different ways. If the
// DSO is dlopen'ed and then dlclose'ed, call_destructors() in
// soinfo_unload() in linker.cpp calls this function. When the DSO
// is a DT_NEEDED one, this function is called as an atexit handler
// when the main nexe exits.
__attribute__((section(".fini"), visibility("hidden")))
void _fini(void) {
  // http://gcc.gnu.org/git/?p=gcc.git;a=blob;f=libgcc/crtstuff.c
  // says this function can be called multiple times when exit() is
  // called in .dtors.
  static int completed;
  if (completed)
    return;
  // This is static not to run the same destructor twice.
  static const structor_fn *iter = &__DTOR_LIST__;
  while (*++iter)
    (**iter)();
  __deregister_frame_info(__EH_FRAME_BEGIN__);
  completed = 1;

  // Change the status of this function in the atexit function list
  // to "already called" by calling __cxa_finalize with the handle.
  // Otherwise, this _fini function will be called when the main nexe
  // exits although dlclose() might have already called for the DSO
  // and text and data segments of the DSO have already gone. Note
  // that this has to be called after |completed| is updated since
  // __cxa_finalize calls back the _fini function.
  __cxa_finalize(&__dso_handle);
}

__attribute__((unused, section(".init"), visibility("hidden")))
void _init(void *irt_query) {
  // This is the max size of "struct object" in
  // http://gcc.gnu.org/git/?p=gcc.git;a=blob;f=libgcc/unwind-dw2-fde.h;h=2bbc60a837c8e3a5d62cdd44f2ae747731f9c8f8;hb=HEAD
  // This buffer is used by libgcc. Unfortunately, it seems there are
  // no way to get the size of this struct.
  // Note that bionic/libc/arch-x86/bionic/crtbegin.S uses 24
  // (sizeof(void*) * 6) for this buffer, but we use 28 here because
  // it seems there can be one more element if
  // DWARF2_OBJECT_END_PTR_EXTENSION is enabled.
  static char buf[sizeof(void*) * 7];
  // Register the info in .eh_frame to libgcc. Though we are disabling
  // C++ exceptions, we want to do this for _Unwind_Backtrace.
  __register_frame_info(__EH_FRAME_BEGIN__, buf);

  // This is defined in crtend.c.
  extern structor_fn __CTOR_END__;
  // As opposed to .dtors, we should iterate .ctors in reversed order.
  // See http://gcc.gnu.org/onlinedocs/gccint/Initialization.html.
  const structor_fn *iter = &__CTOR_END__;
  while (*--iter != (structor_fn)-1) {
    if (*iter == NEXT_CTOR_FUNC_NEEDS_IRT_QUERY_MARKER) {
      // We pass __nacl_irt_query to the function immediately after
      // the magic number. See bionic/linker/linker.h for detail.
      ((void (*)(void *))**--iter)(irt_query);
    } else {
      (**iter)();
    }
  }

  // TODO(crbug.com/404987): Support .fini_array for Bare Metal mode.
  // atexit() requires IRT to be ready. We might need to initialize
  // IRT table in this function instead of in .init_array.
#if !defined(CRTBEGIN_FOR_EXEC) && !defined(BARE_METAL_BIONIC)
  // DT_NEEDED shared objects can be destructed properly by this. We will
  // not use atexit() here because atexit() registers a function with
  // libc.so's __dso_handle which is not what we want to do.
  __cxa_atexit((void (*)(void *))_fini, NULL /* arg */, &__dso_handle);
#endif
}

#include <private/__dso_handle.h>
