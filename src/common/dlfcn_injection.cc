// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include "common/dlfcn_injection.h"

#include <irt_syscalls.h>
#include <private/dl_dst_lib.h>
#include <private/inject_arc_linker_hooks.h>
#include <sys/mman.h>

#include <string>

#include "base/containers/hash_tables.h"
#include "base/strings/string_split.h"
#include "common/alog.h"
#include "common/android_static_libraries.h"
#include "common/arm_syscall.h"
#include "common/wrapped_functions.h"

namespace arc {

namespace {

// A map from wrapped symbol names to their function pointers.
typedef base::hash_map<std::string, void*> SymbolMap;  // NOLINT
SymbolMap* g_wrapped_symbol_map;

// Names of Android's libraries which we statically link to the main nexe.
typedef base::hash_set<std::string> LibraryNameSet;  // NOLINT
LibraryNameSet* g_android_library_names;

// For mmap/munmap, we use --wrap to use posix_translation based
// implementation. We need to convert IRT ABI to libc ABI.
int __nacl_irt_mmap_posix_translation(void** addr, size_t len, int prot,
                                      int flags, int fd, nacl_abi_off_t off) {
  // This is __wrap_mmap call so we will kick posix_translation.
  void* result = mmap(*addr, len, prot, flags, fd, off);
  if (result == MAP_FAILED)
    return errno;
  *addr = result;
  return 0;
}
int __nacl_irt_munmap_posix_translation(void* addr, size_t len) {
  // This is __wrap_munmap call so we will kick posix_translation.
  int result = munmap(addr, len);
  if (result < 0)
    return errno;
  return 0;
}

}  // namespace

void InitDlfcnInjection() {
  g_wrapped_symbol_map = new SymbolMap();
  for (WrappedFunction* p = kWrappedFunctions; p->name; p++) {
    if (!g_wrapped_symbol_map->insert(
          std::make_pair(p->name, reinterpret_cast<void*>(p->func))).second)
      LOG_ALWAYS_FATAL("Duplicated symbol: %s", p->name);
  }

  g_android_library_names = new LibraryNameSet();
  for (const char** p = kAndroidStaticLibraries; *p; p++) {
    // Append ".so" as their shared object versions will be queried.
    const char* kSoSuffix = ".so";
    if (!g_android_library_names->insert(std::string(*p) + kSoSuffix).second)
      LOG_ALWAYS_FATAL("Duplicated library name: %s", *p);
  }

#if defined(USE_NDK_DIRECT_EXECUTION)
  // Syscall numbers (e.g., __NR_mmap) depend on CPU. As we need to
  // handle syscalls called by NDK with ARM's syscall numbers instead
  // of host's, we inject the syscall function for ARM.
  (*g_wrapped_symbol_map)["syscall"] =
      reinterpret_cast<void*>(&RunArmLibcSyscall);
#endif

  // Inject the custom symbol resolver and posix_translation based
  // file operations to the Bionic loader. After we inject the
  // posix_translation based file functions, we use munmap and close
  // based on posix_translation in dlclose. This is safe as we call
  // InitDlfcnInjection before the first dlopen is called, and we do
  // not dlclose DT_NEEDED ELF objects.
  //
  // Note that we have already set up IRT hooks in InitIRTHooks, so
  // __nacl_irt_close, __nacl_irt_open, __nacl_irt_read, and
  // __nacl_irt_write here are not the original IRT functions, but
  // ARC's customized versions which call __wrap_*.
  __arc_linker_hooks hooks = {
    ResolveWrappedSymbol,
    IsStaticallyLinkedSharedObject,
    __nacl_irt_close,
    __nacl_irt_mmap_posix_translation,
    __nacl_irt_munmap_posix_translation,
    __nacl_irt_open,
    __nacl_irt_read,
    __nacl_irt_write,
  };
  __inject_arc_linker_hooks(&hooks);
}

void* ResolveWrappedSymbol(const char* symbol) {
  SymbolMap::const_iterator found = g_wrapped_symbol_map->find(symbol);
  return found != g_wrapped_symbol_map->end() ? found->second : NULL;
}

int IsStaticallyLinkedSharedObject(const char* filename) {
  LibraryNameSet::const_iterator found =
      g_android_library_names->find(filename);
  return found != g_android_library_names->end();
}

}  // namespace arc
