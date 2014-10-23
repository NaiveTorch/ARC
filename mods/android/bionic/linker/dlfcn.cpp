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

#include "linker.h"

#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

#include <bionic/pthread_internal.h>
#include <private/bionic_tls.h>
#include <private/ScopedPthreadMutexLocker.h>
#include <private/ThreadLocalBuffer.h>
// ARC MOD BEGIN
// Add a include for __inject_arc_linker_hooks.
#include <private/inject_arc_linker_hooks.h>
// ARC MOD END

/* This file hijacks the symbols stubbed out in libdl.so. */

static pthread_mutex_t gDlMutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;

static const char* __bionic_set_dlerror(char* new_value) {
  void* tls = const_cast<void*>(__get_tls());
  char** dlerror_slot = &reinterpret_cast<char**>(tls)[TLS_SLOT_DLERROR];

  const char* old_value = *dlerror_slot;
  *dlerror_slot = new_value;
  return old_value;
}

static void __bionic_format_dlerror(const char* msg, const char* detail) {
  char* buffer = __get_thread()->dlerror_buffer;
  strlcpy(buffer, msg, __BIONIC_DLERROR_BUFFER_SIZE);
  if (detail != NULL) {
    strlcat(buffer, ": ", __BIONIC_DLERROR_BUFFER_SIZE);
    strlcat(buffer, detail, __BIONIC_DLERROR_BUFFER_SIZE);
  }

  __bionic_set_dlerror(buffer);
}

const char* dlerror() {
  const char* old_value = __bionic_set_dlerror(NULL);
  return old_value;
}

void android_update_LD_LIBRARY_PATH(const char* ld_library_path) {
  ScopedPthreadMutexLocker locker(&gDlMutex);
  do_android_update_LD_LIBRARY_PATH(ld_library_path);
}

void* dlopen(const char* filename, int flags) {
  ScopedPthreadMutexLocker locker(&gDlMutex);
  soinfo* result = do_dlopen(filename, flags);
  if (result == NULL) {
    __bionic_format_dlerror("dlopen failed", linker_get_error_buffer());
    return NULL;
  }
  return result;
}

void* dlsym(void* handle, const char* symbol) {
  ScopedPthreadMutexLocker locker(&gDlMutex);

  if (handle == NULL) {
    __bionic_format_dlerror("dlsym library handle is null", NULL);
    return NULL;
  }
  if (symbol == NULL) {
    __bionic_format_dlerror("dlsym symbol name is null", NULL);
    return NULL;
  }

  soinfo* found = NULL;
  Elf32_Sym* sym = NULL;
  if (handle == RTLD_DEFAULT) {
    sym = dlsym_linear_lookup(symbol, &found, NULL);
  } else if (handle == RTLD_NEXT) {
    void* ret_addr = __builtin_return_address(0);
    soinfo* si = find_containing_library(ret_addr);

    sym = NULL;
    if (si && si->next) {
      sym = dlsym_linear_lookup(symbol, &found, si->next);
    }
  } else {
    found = reinterpret_cast<soinfo*>(handle);
    sym = dlsym_handle_lookup(found, symbol);
  }

  if (sym != NULL) {
    unsigned bind = ELF32_ST_BIND(sym->st_info);

    // ARC MOD BEGIN UPSTREAM bionic-allow-weak-in-dlsym
    // Allow weak symbols as return values of dlsym. Without this,
    // dlsym("isalpha") may fail if 1. you are building your program
    // with g++ (not gcc), 2. you have -DNDEBUG, and 3. your
    // program calls isalpha directly. This issue happens even on
    // a real android device.
    if ((bind == STB_GLOBAL || bind == STB_WEAK) && sym->st_shndx != 0) {
    // ARC MOD END UPSTREAM
      unsigned ret = sym->st_value + found->load_bias;
      return (void*) ret;
    }

    __bionic_format_dlerror("symbol found but not global", symbol);
    return NULL;
  } else {
    __bionic_format_dlerror("undefined symbol", symbol);
    return NULL;
  }
}

int dladdr(const void* addr, Dl_info* info) {
  ScopedPthreadMutexLocker locker(&gDlMutex);

  // Determine if this address can be found in any library currently mapped.
  soinfo* si = find_containing_library(addr);
  if (si == NULL) {
    return 0;
  }

  memset(info, 0, sizeof(Dl_info));

  info->dli_fname = si->name;
  // Address at which the shared object is loaded.
  info->dli_fbase = (void*) si->base;

  // Determine if any symbol in the library contains the specified address.
  Elf32_Sym *sym = dladdr_find_symbol(si, addr);
  if (sym != NULL) {
    info->dli_sname = si->strtab + sym->st_name;
    info->dli_saddr = (void*)(si->load_bias + sym->st_value);
  }

  return 1;
}

int dlclose(void* handle) {
  ScopedPthreadMutexLocker locker(&gDlMutex);
  return do_dlclose(reinterpret_cast<soinfo*>(handle));
}

#if defined(ANDROID_ARM_LINKER)
// ARC MOD BEGIN
// Add dl_iterate_phdr and __inject_arc_linker_hooks for ARM.
//   0000000 00011111 111112 22222222 2333333 3333444444444455555555556666666 666777777777788888888 8899999999990000 0000001111111111222222222233
//   0123456 78901234 567890 12345678 9012345 6789012345678901234567890123456 789012345678901234567 8901234567890123 4567890123456789012345678901
#define ANDROID_LIBDL_STRTAB \
    "dlopen\0dlclose\0dlsym\0dlerror\0dladdr\0android_update_LD_LIBRARY_PATH\0dl_unwind_find_exidx\0dl_iterate_phdr\0__inject_arc_linker_hooks\0"

// Add x86-64 support.
#elif defined(ANDROID_X86_LINKER) || defined(ANDROID_MIPS_LINKER) \
  || defined(ANDROID_X86_64_LINKER)
// Add __inject_arc_linker_hooks.
// See bionic/libc/private/inject_arc_linker_hooks.h for detail.
//   0000000 00011111 111112 22222222 2333333 3333444444444455555555556666666 6667777777777888 8888888999999999900000000001
//   0123456 78901234 567890 12345678 9012345 6789012345678901234567890123456 7890123456789012 3456789012345678901234567890
#define ANDROID_LIBDL_STRTAB \
    "dlopen\0dlclose\0dlsym\0dlerror\0dladdr\0android_update_LD_LIBRARY_PATH\0dl_iterate_phdr\0__inject_arc_linker_hooks\0"
// ARC MOD END
#else
#error Unsupported architecture. Only ARM, MIPS, and x86 are presently supported.
#endif

// ARC MOD BEGIN
// 64bit NaCl uses ELF64 but its pointer type is 32bit. This means we
// cannot initialize a 64bit integer in Elf64_Sym (st_value) by a
// pointer. Specifically, on x86-64 NaCl, we cannot compile code like
//
// Elf64_Sym sym = { st_value: (Elf64_Addr)&sym };
//
// So, we define another struct Elf64_Sym_NaCl. This is very similar
// to Elf64_Sym, but its st_value is divided into two 32bit integers
// (i.e., st_value and st_value_padding). This is only used to define
// |libdl_symtab| below. |libdl_symtab| will be passed to
// libdl_info.symtab in this file. Other code will not use this and
// use normal Elf64_Sym instead.
#if defined(ANDROID_X86_64_LINKER) && defined(__native_client__)
struct Elf64_Sym_NaCl {
  Elf64_Word st_name;
  unsigned char st_info;
  unsigned char st_other;
  Elf64_Half st_shndx;
  // Put lower bits first because we are little endian.
  unsigned st_value;
  // We will not fill this field, so this will be initialized to zero.
  unsigned st_value_padding;
  Elf64_Xword st_size;
};

// Static assertions for the layout of Elf64_Sym_NaCl.
#define STATIC_ASSERT(cond, name) \
  struct StaticAssert_ ## name { char name[(cond) ? 1 : -1]; }
STATIC_ASSERT(sizeof(Elf64_Sym_NaCl) == sizeof(Elf64_Sym),
              SizeOf_Elf64_Sym_NaCl);
STATIC_ASSERT(offsetof(Elf64_Sym_NaCl, st_value) ==
              offsetof(Elf64_Sym, st_value),
              OffsetOf_st_value);
STATIC_ASSERT(offsetof(Elf64_Sym_NaCl, st_size) ==
              offsetof(Elf64_Sym, st_size),
              OffsetOf_st_size);

// Remove map from Elf32_Addr to Elf64_Addr defined in linker.h.
#undef Elf32_Addr

// Modified for Elf64_Sym_NaCl.
#define ELF32_SYM_INITIALIZER(name_offset, value, shndx)            \
  { /* st_name */ name_offset,                                      \
    /* st_info */ (shndx == 0) ? 0 : (STB_GLOBAL << 4),             \
    /* st_other */ 0,                                               \
    /* st_shndx */ shndx,                                           \
    /* st_value */ reinterpret_cast<Elf32_Addr>(reinterpret_cast<void*>(value)), \
    /* st_value_padding */ 0,                                       \
    /* st_size */ 0 }

static Elf64_Sym_NaCl gLibDlSymtab[] = {
#else
// ARC MOD END
// name_offset: starting index of the name in libdl_info.strtab
#define ELF32_SYM_INITIALIZER(name_offset, value, shndx) \
    { name_offset, \
      reinterpret_cast<Elf32_Addr>(reinterpret_cast<void*>(value)), \
      /* st_size */ 0, \
      (shndx == 0) ? 0 : (STB_GLOBAL << 4), \
      /* st_other */ 0, \
      shndx }

static Elf32_Sym gLibDlSymtab[] = {
// ARC MOD BEGIN
#endif
// ARC MOD END
  // Total length of libdl_info.strtab, including trailing 0.
  // This is actually the STH_UNDEF entry. Technically, it's
  // supposed to have st_name == 0, but instead, it points to an index
  // in the strtab with a \0 to make iterating through the symtab easier.
  ELF32_SYM_INITIALIZER(sizeof(ANDROID_LIBDL_STRTAB) - 1, NULL, 0),
  ELF32_SYM_INITIALIZER( 0, &dlopen, 1),
  ELF32_SYM_INITIALIZER( 7, &dlclose, 1),
  ELF32_SYM_INITIALIZER(15, &dlsym, 1),
  ELF32_SYM_INITIALIZER(21, &dlerror, 1),
  ELF32_SYM_INITIALIZER(29, &dladdr, 1),
  ELF32_SYM_INITIALIZER(36, &android_update_LD_LIBRARY_PATH, 1),
#if defined(ANDROID_ARM_LINKER)
  ELF32_SYM_INITIALIZER(67, &dl_unwind_find_exidx, 1),
  // ARC MOD BEGIN
  // Add dl_iterate_phdr and __inject_arc_linker_hooks for ARM.
  ELF32_SYM_INITIALIZER(88, &dl_iterate_phdr, 1),
  ELF32_SYM_INITIALIZER(104, &__inject_arc_linker_hooks, 1),
  // Add x86-64 support.
#elif defined(ANDROID_X86_LINKER) || defined(ANDROID_MIPS_LINKER) \
  || defined(ANDROID_X86_64_LINKER)
  // ARC MOD END
  ELF32_SYM_INITIALIZER(67, &dl_iterate_phdr, 1),
  // ARC MOD BEGIN
  // Add dl_iterate_phdr and __inject_arc_linker_hooks.
  ELF32_SYM_INITIALIZER(83, &__inject_arc_linker_hooks, 1),
  // ARC MOD END
#endif
};

// Fake out a hash table with a single bucket.
// A search of the hash table will look through
// gLibDlSymtab starting with index [1], then
// use gLibDlChains to find the next index to
// look at.  gLibDlChains should be set up to
// walk through every element in gLibDlSymtab,
// and then end with 0 (sentinel value).
//
// That is, gLibDlChains should look like
// { 0, 2, 3, ... N, 0 } where N is the number
// of actual symbols, or nelems(gLibDlSymtab)-1
// (since the first element of gLibDlSymtab is not
// a real symbol).
//
// (see soinfo_elf_lookup())
//
// Note that adding any new symbols here requires
// stubbing them out in libdl.
static unsigned gLibDlBuckets[1] = { 1 };
// ARC MOD BEGIN
// Size now varies because dl_iterate_phdr and
// __inject_arc_linker_hooks have been added for ARM.
#ifdef ANDROID_ARM_LINKER
static unsigned gLibDlChains[10] = { 0, 2, 3, 4, 5, 6, 7, 8, 9, 0 };
#else
// Size now varies because _arc_linker_hooks has been added.
static unsigned gLibDlChains[9] = { 0, 2, 3, 4, 5, 6, 7, 8, 0 };
#endif
// ARC MOD END

// This is used by the dynamic linker. Every process gets these symbols for free.
soinfo libdl_info = {
    "libdl.so",

    phdr: 0, phnum: 0,
    entry: 0, base: 0, size: 0,
    unused1: 0, dynamic: 0, unused2: 0, unused3: 0,
    next: 0,

    flags: FLAG_LINKED,

    strtab: ANDROID_LIBDL_STRTAB,
    // ARC MOD BEGIN
#if defined(ANDROID_X86_64_LINKER) && defined(__native_client__)
    // Add a cast for x86-64.
    symtab: reinterpret_cast<Elf64_Sym*>(gLibDlSymtab),
#else
    // ARC MOD END
    symtab: gLibDlSymtab,
    // ARC MOD BEGIN
#endif
    // ARC MOD END

    nbucket: 1,
    // ARC MOD BEGIN
    // Support for variable-length nchain has already been added upstream.
    nchain: sizeof(gLibDlChains) / sizeof(gLibDlChains[0]),
    // ARC MOD END
    bucket: gLibDlBuckets,
    chain: gLibDlChains,

    plt_got: 0, plt_rel: 0, plt_rel_count: 0, rel: 0, rel_count: 0,
    preinit_array: 0, preinit_array_count: 0, init_array: 0, init_array_count: 0,
    fini_array: 0, fini_array_count: 0, init_func: 0, fini_func: 0,

#if defined(ANDROID_ARM_LINKER)
    ARM_exidx: 0, ARM_exidx_count: 0,
#elif defined(ANDROID_MIPS_LINKER)
    mips_symtabno: 0, mips_local_gotno: 0, mips_gotsym: 0,
#endif

    ref_count: 0,
    { l_addr: 0, l_name: 0, l_ld: 0, l_next: 0, l_prev: 0, },
    constructors_called: false,
    load_bias: 0,
    has_text_relocations: false,
    has_DT_SYMBOLIC: true,
    // ARC MOD BEGIN
    // Initialize is_ndk.
#if defined(USE_NDK_DIRECT_EXECUTION)
    is_ndk: false,
#endif
    // ARC MOD END
};
