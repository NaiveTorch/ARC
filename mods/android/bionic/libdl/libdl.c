/*
 * Copyright (C) 2007 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <dlfcn.h>
// ARC MOD BEGIN
// Add a include for __inject_arc_linker_hooks.
#include <private/inject_arc_linker_hooks.h>
// ARC MOD END
/* These are stubs for functions that are actually defined
 * in the dynamic linker (dlfcn.c), and hijacked at runtime.
 */
void *dlopen(const char *filename, int flag) { return 0; }
const char *dlerror(void) { return 0; }
void *dlsym(void *handle, const char *symbol) { return 0; }
int dladdr(const void *addr, Dl_info *info) { return 0; }
int dlclose(void *handle) { return 0; }

void android_update_LD_LIBRARY_PATH(const char* ld_library_path) { }
// ARC MOD BEGIN
// Add __inject_arc_linker_hooks.
void __inject_arc_linker_hooks(__arc_linker_hooks* hooks) { }
// ARC MOD END

#if defined(__arm__)

void *dl_unwind_find_exidx(void *pc, int *pcount) { return 0; }
// ARC MOD BEGIN
#endif
// Add __x86_64__ and __arm__.
#if defined(__i386__) || defined(__mips__) \
  || defined(__x86_64__) || defined(__arm__)
// ARC MOD END
/* we munge the cb definition so we don't have to include any headers here.
 * It won't affect anything since these are just symbols anyway */
int dl_iterate_phdr(int (*cb)(void *info, void *size, void *data), void *data) { return 0; }

#else
#error Unsupported architecture. Only mips, arm and x86 are supported.
#endif
