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
// Define __inject_arc_linker_hooks. This allows ARC to customize
// the behavior of the Bionic loader for NDK.
//

#ifndef _ANDROID_BIONIC_LIBC_PRIVATE_INJECT_ARC_LINKER_HOOKS_H
#define _ANDROID_BIONIC_LIBC_PRIVATE_INJECT_ARC_LINKER_HOOKS_H

#include <irt_syscalls.h>
#include <sys/cdefs.h>

__BEGIN_DECLS

typedef struct {
  // Once this function has been injected, the Bionic loader runs this
  // function first when it looks up a symbol. If this function
  // returns a non-NULL value, the Bionic loader will use it.
  // Otherwise, it falls back to the normal symbol lookup.
  void* (*resolve_symbol)(const char* symbol);
  int (*is_statically_linked)(const char* filename);
  // The following file related functions can be called by the Bionic
  // loader.
  typeof(__nacl_irt_close) nacl_irt_close;
  typeof(__nacl_irt_mmap) nacl_irt_mmap;
  typeof(__nacl_irt_munmap) nacl_irt_munmap;
  typeof(__nacl_irt_open) nacl_irt_open;
  typeof(__nacl_irt_read) nacl_irt_read;
  typeof(__nacl_irt_write) nacl_irt_write;
} __arc_linker_hooks;

// This function must be called before the first pthread_create.
// You must not call dlopen before this function either. If we dlopen
// a shared object before this function, the dlopen uses the raw open
// and mmap implementations, so the hooked close and munmap cannot be
// used for it.
void __inject_arc_linker_hooks(__arc_linker_hooks* hooks);

__END_DECLS

#endif  // _ANDROID_BIONIC_LIBC_PRIVATE_INJECT_ARC_LINKER_HOOKS_H
