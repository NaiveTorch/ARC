/*
 * Copyright (C) 2008, 2009 The Android Open Source Project
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

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/auxvec.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/atomics.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

// Private C library headers.
#include <private/bionic_tls.h>
#include <private/KernelArgumentBlock.h>
#include <private/ScopedPthreadMutexLocker.h>

// ARC MOD BEGIN
// Add includes.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#include <nacl_dyncode.h>
#include <private/at_sysinfo.h>
#include <private/dl_dst_lib.h>
#include <private/inject_arc_linker_hooks.h>
#include <private/irt_query_marker.h>
// TODO(crbug.com/354290): Remove this include. This is only for GDB hack.
#if defined(BARE_METAL_BIONIC)
#include <sys/syscall.h>
#endif
#endif
// ARC MOD END
#include "linker.h"
#include "linker_debug.h"
#include "linker_environ.h"
#include "linker_phdr.h"

// ARC MOD BEGIN
// Add a function prototype.
#if defined(__native_client__)
void phdr_table_get_nacl_gapped_layout_info(
    const Elf32_Phdr* phdr_table,
    size_t phdr_count,
    size_t* code_first,
    size_t* code_size,
    size_t* data_first,
    size_t* data_size);
#endif  // __native_client__

// Add the forward declaration for load_main_binary.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
static void load_main_binary(KernelArgumentBlock& args);
#endif

static void* (*g_resolve_symbol)(const char* symbol);
static int (*g_is_statically_linked)(const char* filename);

// TODO(crbug.com/364344): Remove /vendor/lib.
const char kVendorLibDir[] = "/vendor/lib/";
// ARC MOD END
/* Assume average path length of 64 and max 8 paths */
#define LDPATH_BUFSIZE 512
#define LDPATH_MAX 8

#define LDPRELOAD_BUFSIZE 512
#define LDPRELOAD_MAX 8

/* >>> IMPORTANT NOTE - READ ME BEFORE MODIFYING <<<
 *
 * Do NOT use malloc() and friends or pthread_*() code here.
 * Don't use printf() either; it's caused mysterious memory
 * corruption in the past.
 * The linker runs before we bring up libc and it's easiest
 * to make sure it does not depend on any complex libc features
 *
 * open issues / todo:
 *
 * - are we doing everything we should for ARM_COPY relocations?
 * - cleaner error reporting
 * - after linking, set as much stuff as possible to READONLY
 *   and NOEXEC
 */
// ARC MOD BEGIN
// For showing some performance stats when --logging=bionic-loader is
// specified.
#if defined(BIONIC_LOADER_LOGGING)

template <int line_number>
class ScopedElapsedTimePrinter {
public:
  ScopedElapsedTimePrinter(const char* category, const char* name)
    : category_(category), name_(name) {
    gettimeofday(&t0_, NULL);
  }

  ~ScopedElapsedTimePrinter() {
    timeval t1;
    gettimeofday(&t1, NULL);
    const int elapsed =
      (((long long)t1.tv_sec * 1000000LL) + (long long)t1.tv_usec) -
      (((long long)t0_.tv_sec * 1000000LL) + (long long)t0_.tv_usec);
    cumulative_ += elapsed;
    PRINT("LINKER TIME: %s %s: %d us (%d ms cumulative for line:%d)",
          category_, name_, elapsed, cumulative_ / 1000, line_number);
  }

private:
  static int cumulative_;  // held per |line_number|

  const char* category_;
  const char* name_;
  timeval t0_;
};

template <int line_number>
int ScopedElapsedTimePrinter<line_number>::cumulative_ = 0;

#else  // BIONIC_LOADER_LOGGING

template <int line_number>
class ScopedElapsedTimePrinter {
public:
  ScopedElapsedTimePrinter(const char* category, const char* name) {}
};

#endif  // BIONIC_LOADER_LOGGING
// ARC MOD END

static bool soinfo_link_image(soinfo* si);

// We can't use malloc(3) in the dynamic linker. We use a linked list of anonymous
// maps, each a single page in size. The pages are broken up into as many struct soinfo
// objects as will fit, and they're all threaded together on a free list.
#define SOINFO_PER_POOL ((PAGE_SIZE - sizeof(soinfo_pool_t*)) / sizeof(soinfo))
struct soinfo_pool_t {
  soinfo_pool_t* next;
  soinfo info[SOINFO_PER_POOL];
};
static struct soinfo_pool_t* gSoInfoPools = NULL;
static soinfo* gSoInfoFreeList = NULL;

static soinfo* solist = &libdl_info;
static soinfo* sonext = &libdl_info;
static soinfo* somain; /* main process, always the one after libdl_info */

static const char* const gSoPaths[] = {
  "/vendor/lib",
  "/system/lib",
  NULL
};

static char gLdPathsBuffer[LDPATH_BUFSIZE];
static const char* gLdPaths[LDPATH_MAX + 1];

static char gLdPreloadsBuffer[LDPRELOAD_BUFSIZE];
static const char* gLdPreloadNames[LDPRELOAD_MAX + 1];

static soinfo* gLdPreloads[LDPRELOAD_MAX + 1];

// ARC MOD BEGIN
// When you port the linker MODs to a newer Bionic release, you might want
// to initialize |gLdDebugVerbosity| with 3 to get full debug logs (such as
// DL_ERR) from the linker. As neither sel_ldr nor nacl_helper
// propagates environment variables, you need to modify this parameter
// directly. Note that this value will be updated to -1 in
// __linker_init for --disable-debug-code build.
//
// run_under_gdb.py is also useful to debug crashes when porting the linker:
//  $ ninja out/target/nacl_x86_64_dbg/bionic_tests/loader_test
//  $ src/build/run_under_gdb.py
//     out/target/nacl_x86_64_dbg/bionic_tests/loader_test
// ARC MOD END
__LIBC_HIDDEN__ int gLdDebugVerbosity;

__LIBC_HIDDEN__ abort_msg_t* gAbortMessage = NULL; // For debuggerd.

enum RelocationKind {
    kRelocAbsolute = 0,
    kRelocRelative,
    kRelocCopy,
    kRelocSymbol,
    kRelocMax
};

#if STATS
struct linker_stats_t {
    int count[kRelocMax];
};

static linker_stats_t linker_stats;

static void count_relocation(RelocationKind kind) {
    ++linker_stats.count[kind];
}
#else
static void count_relocation(RelocationKind) {
}
#endif

#if COUNT_PAGES
static unsigned bitmask[4096];
#define MARK(offset) \
    do { \
        bitmask[((offset) >> 12) >> 3] |= (1 << (((offset) >> 12) & 7)); \
    } while(0)
#else
#define MARK(x) do {} while (0)
#endif

// You shouldn't try to call memory-allocating functions in the dynamic linker.
// Guard against the most obvious ones.
#define DISALLOW_ALLOCATION(return_type, name, ...) \
    return_type name __VA_ARGS__ \
    { \
        const char* msg = "ERROR: " #name " called from the dynamic linker!\n"; \
        __libc_format_log(ANDROID_LOG_FATAL, "linker", "%s", msg); \
        write(2, msg, strlen(msg)); \
        abort(); \
    }
#define UNUSED __attribute__((unused))
DISALLOW_ALLOCATION(void*, malloc, (size_t u UNUSED));
DISALLOW_ALLOCATION(void, free, (void* u UNUSED));
DISALLOW_ALLOCATION(void*, realloc, (void* u1 UNUSED, size_t u2 UNUSED));
DISALLOW_ALLOCATION(void*, calloc, (size_t u1 UNUSED, size_t u2 UNUSED));

static char tmp_err_buf[768];
static char __linker_dl_err_buf[768];

char* linker_get_error_buffer() {
  return &__linker_dl_err_buf[0];
}

size_t linker_get_error_buffer_size() {
  return sizeof(__linker_dl_err_buf);
}

/*
 * This function is an empty stub where GDB locates a breakpoint to get notified
 * about linker activity.
 */
extern "C" void __attribute__((noinline)) __attribute__((visibility("default"))) rtld_db_dlactivity();

// ARC MOD BEGIN
// Cast rtld_db_dlactivity to Elf64_Addr on x86-64 NaCl.
#if defined(ANDROID_X86_64_LINKER) && defined(__native_client__)
static r_debug _r_debug = {1, NULL, (Elf64_Addr)&rtld_db_dlactivity,
                           RT_CONSISTENT, 0};
#else
// ARC MOD END
static r_debug _r_debug = {1, NULL, &rtld_db_dlactivity, RT_CONSISTENT, 0};
// ARC MOD BEGIN
#endif
// ARC MOD END
static link_map_t* r_debug_tail = 0;

static pthread_mutex_t gDebugMutex = PTHREAD_MUTEX_INITIALIZER;

static void insert_soinfo_into_debug_map(soinfo * info) {
    // Copy the necessary fields into the debug structure.
    link_map_t* map = &(info->link_map);
    // ARC MOD BEGIN
    // TODO(mazda): Verify this code is compatible with our minidump tool.
    // See also 'git show 914cd7f7'.
    // ARC MOD END
    map->l_addr = info->base;
    map->l_name = (char*) info->name;
    map->l_ld = (uintptr_t)info->dynamic;

    /* Stick the new library at the end of the list.
     * gdb tends to care more about libc than it does
     * about leaf libraries, and ordering it this way
     * reduces the back-and-forth over the wire.
     */
    if (r_debug_tail) {
        r_debug_tail->l_next = map;
        map->l_prev = r_debug_tail;
        map->l_next = 0;
    } else {
        _r_debug.r_map = map;
        map->l_prev = 0;
        map->l_next = 0;
    }
    r_debug_tail = map;
}

static void remove_soinfo_from_debug_map(soinfo* info) {
    link_map_t* map = &(info->link_map);

    if (r_debug_tail == map) {
        r_debug_tail = map->l_prev;
    }

    if (map->l_prev) {
        map->l_prev->l_next = map->l_next;
    }
    if (map->l_next) {
        map->l_next->l_prev = map->l_prev;
    }
}

static void notify_gdb_of_load(soinfo* info) {
    // ARC MOD BEGIN
    // Always copy the necessary fields into the debug
    // structure. The original Bionic loader fills these fields in
    // insert_soinfo_into_debug_map, but we do not call this function
    // for ET_EXEC or Bare Metal mode. The behavior of the original
    // Bionic loader is OK because info->link_map is not used on normal
    // Linux. The loader does not need to tell the information of the
    // main binary to GDB.
    // TODO(crbug.com/323864): Enable this on NaCl. Currently this is
    // excluded to workaround the issue of minidumps not being generated.
#if defined(BARE_METAL_BIONIC)
    link_map_t* map = &(info->link_map);
    map->l_addr = info->base;
    if (!map->l_name) {
      // main binary's argv[0] is /lib/main.nexe, here it's main.nexe,
      // keep /lib/main.nexe here.  For shared libraries, it is NULL,
      // so give it some value.
      map->l_name = info->name;
    }
    map->l_ld = (uintptr_t)info->dynamic;
    // Ask the Bare Metal loader to interact with GDB.
    if (__bare_metal_irt_notify_gdb_of_load) {
        // GDB has already known about the Bionic loader.
        if (info->flags & FLAG_LINKER)
            return;
        __bare_metal_irt_notify_gdb_of_load(
            reinterpret_cast<struct link_map*>(map));
    }
#else
    // ARC MOD END
    if (info->flags & FLAG_EXE) {
        // GDB already knows about the main executable
        return;
    }

    ScopedPthreadMutexLocker locker(&gDebugMutex);

    _r_debug.r_state = RT_ADD;
    rtld_db_dlactivity();

    insert_soinfo_into_debug_map(info);

    _r_debug.r_state = RT_CONSISTENT;
    rtld_db_dlactivity();
    // ARC MOD BEGIN
#endif
    // ARC MOD END
}

static void notify_gdb_of_unload(soinfo* info) {
    // ARC MOD BEGIN
    // Ask the Bare Metal loader to interact with GDB.
#if defined(BARE_METAL_BIONIC)
    if (__bare_metal_irt_notify_gdb_of_unload) {
        __bare_metal_irt_notify_gdb_of_unload(
            reinterpret_cast<struct link_map*>(&info->link_map));
    }
#else
    // ARC MOD END
    if (info->flags & FLAG_EXE) {
        // GDB already knows about the main executable
        return;
    }

    ScopedPthreadMutexLocker locker(&gDebugMutex);

    _r_debug.r_state = RT_DELETE;
    rtld_db_dlactivity();

    remove_soinfo_from_debug_map(info);

    _r_debug.r_state = RT_CONSISTENT;
    rtld_db_dlactivity();
    // ARC MOD BEGIN
#endif
    // ARC MOD END
}

void notify_gdb_of_libraries() {
    // ARC MOD BEGIN
    // Ask the Bare Metal loader to interact with GDB.
#if defined(BARE_METAL_BIONIC)
    if (__bare_metal_irt_notify_gdb_of_libraries)
        __bare_metal_irt_notify_gdb_of_libraries();
#else
    // ARC MOD END
    _r_debug.r_state = RT_ADD;
    rtld_db_dlactivity();
    _r_debug.r_state = RT_CONSISTENT;
    rtld_db_dlactivity();
    // ARC MOD BEGIN
#endif
    // ARC MOD END
}

static bool ensure_free_list_non_empty() {
  if (gSoInfoFreeList != NULL) {
    return true;
  }

  // Allocate a new pool.
  soinfo_pool_t* pool = reinterpret_cast<soinfo_pool_t*>(mmap(NULL, sizeof(*pool),
                                                              PROT_READ|PROT_WRITE,
                                                              MAP_PRIVATE|MAP_ANONYMOUS, 0, 0));
  if (pool == MAP_FAILED) {
    return false;
  }

  // Add the pool to our list of pools.
  pool->next = gSoInfoPools;
  gSoInfoPools = pool;

  // Chain the entries in the new pool onto the free list.
  gSoInfoFreeList = &pool->info[0];
  soinfo* next = NULL;
  for (int i = SOINFO_PER_POOL - 1; i >= 0; --i) {
    pool->info[i].next = next;
    next = &pool->info[i];
  }

  return true;
}

static void set_soinfo_pool_protection(int protection) {
  for (soinfo_pool_t* p = gSoInfoPools; p != NULL; p = p->next) {
    if (mprotect(p, sizeof(*p), protection) == -1) {
      abort(); // Can't happen.
    }
  }
}

static soinfo* soinfo_alloc(const char* name) {
  if (strlen(name) >= SOINFO_NAME_LEN) {
    DL_ERR("library name \"%s\" too long", name);
    return NULL;
  }

  if (!ensure_free_list_non_empty()) {
    DL_ERR("out of memory when loading \"%s\"", name);
    return NULL;
  }

  // Take the head element off the free list.
  soinfo* si = gSoInfoFreeList;
  gSoInfoFreeList = gSoInfoFreeList->next;

  // Initialize the new element.
  memset(si, 0, sizeof(soinfo));
  strlcpy(si->name, name, sizeof(si->name));
  sonext->next = si;
  sonext = si;

  TRACE("name %s: allocated soinfo @ %p", name, si);
  return si;
}

static void soinfo_free(soinfo* si)
{
    if (si == NULL) {
        return;
    }

    soinfo *prev = NULL, *trav;

    TRACE("name %s: freeing soinfo @ %p", si->name, si);

    for (trav = solist; trav != NULL; trav = trav->next) {
        if (trav == si)
            break;
        prev = trav;
    }
    if (trav == NULL) {
        /* si was not in solist */
        DL_ERR("name \"%s\" is not in solist!", si->name);
        return;
    }

    /* prev will never be NULL, because the first entry in solist is
       always the static libdl_info.
    */
    prev->next = si->next;
    if (si == sonext) {
        sonext = prev;
    }
    si->next = gSoInfoFreeList;
    gSoInfoFreeList = si;
}


static void parse_path(const char* path, const char* delimiters,
                       const char** array, char* buf, size_t buf_size, size_t max_count) {
  if (path == NULL) {
    return;
  }

  size_t len = strlcpy(buf, path, buf_size);

  size_t i = 0;
  char* buf_p = buf;
  while (i < max_count && (array[i] = strsep(&buf_p, delimiters))) {
    if (*array[i] != '\0') {
      ++i;
    }
  }

  // Forget the last path if we had to truncate; this occurs if the 2nd to
  // last char isn't '\0' (i.e. wasn't originally a delimiter).
  if (i > 0 && len >= buf_size && buf[buf_size - 2] != '\0') {
    array[i - 1] = NULL;
  } else {
    array[i] = NULL;
  }
}

static void parse_LD_LIBRARY_PATH(const char* path) {
  parse_path(path, ":", gLdPaths,
             gLdPathsBuffer, sizeof(gLdPathsBuffer), LDPATH_MAX);
}

static void parse_LD_PRELOAD(const char* path) {
  // We have historically supported ':' as well as ' ' in LD_PRELOAD.
  parse_path(path, " :", gLdPreloadNames,
             gLdPreloadsBuffer, sizeof(gLdPreloadsBuffer), LDPRELOAD_MAX);
}

#ifdef ANDROID_ARM_LINKER

/* For a given PC, find the .so that it belongs to.
 * Returns the base address of the .ARM.exidx section
 * for that .so, and the number of 8-byte entries
 * in that section (via *pcount).
 *
 * Intended to be called by libc's __gnu_Unwind_Find_exidx().
 *
 * This function is exposed via dlfcn.cpp and libdl.so.
 */
_Unwind_Ptr dl_unwind_find_exidx(_Unwind_Ptr pc, int *pcount)
{
    soinfo *si;
    unsigned addr = (unsigned)pc;

    for (si = solist; si != 0; si = si->next){
        if ((addr >= si->base) && (addr < (si->base + si->size))) {
            *pcount = si->ARM_exidx_count;
            return (_Unwind_Ptr)si->ARM_exidx;
        }
    }
   *pcount = 0;
    return NULL;
}

// ARC MOD BEGIN
#endif
// Add dl_iterate_phdr for x86-64 and arm.
#if defined(ANDROID_X86_LINKER) || defined(ANDROID_MIPS_LINKER) \
    || defined(ANDROID_X86_64_LINKER) || defined(ANDROID_ARM_LINKER)
// ARC MOD END

/* Here, we only have to provide a callback to iterate across all the
 * loaded libraries. gcc_eh does the rest. */
int
dl_iterate_phdr(int (*cb)(dl_phdr_info *info, size_t size, void *data),
                void *data)
{
    int rv = 0;
    for (soinfo* si = solist; si != NULL; si = si->next) {
        dl_phdr_info dl_info;
        dl_info.dlpi_addr = si->link_map.l_addr;
        dl_info.dlpi_name = si->link_map.l_name;
        dl_info.dlpi_phdr = si->phdr;
        dl_info.dlpi_phnum = si->phnum;
        rv = cb(&dl_info, sizeof(dl_phdr_info), data);
        if (rv != 0) {
            break;
        }
    }
    return rv;
}

#endif

static Elf32_Sym* soinfo_elf_lookup(soinfo* si, unsigned hash, const char* name) {
    Elf32_Sym* symtab = si->symtab;
    const char* strtab = si->strtab;

    TRACE_TYPE(LOOKUP, "SEARCH %s in %s@0x%08x %08x %d",
               // ARC MOD BEGIN
               // Add a cast for x86-64.
               name, si->name, (uint32_t)si->base, hash, hash % si->nbucket);
               // ARC MOD END

    for (unsigned n = si->bucket[hash % si->nbucket]; n != 0; n = si->chain[n]) {
        Elf32_Sym* s = symtab + n;
        if (strcmp(strtab + s->st_name, name)) continue;

            /* only concern ourselves with global and weak symbol definitions */
        // ARC MOD BEGIN
        // Use ELFW(ST_BIND) instead of ELF32_ST_BIND.
        switch (ELFW(ST_BIND)(s->st_info)) {
        // ARC MOD END
        case STB_GLOBAL:
        case STB_WEAK:
        // ARC MOD BEGIN
        // We treat STB_GNU_UNIQUE as STB_GLOBAL.
        // TODO(crbug.com/306079): Check if this is OK and implement
        // STB_GNU_UNIQUE support if necessary.
#define STB_GNU_UNIQUE 10
        case STB_GNU_UNIQUE:
        // ARC MOD END
            if (s->st_shndx == SHN_UNDEF) {
                continue;
            }

            TRACE_TYPE(LOOKUP, "FOUND %s in %s (%08x) %d",
                       // ARC MOD BEGIN
                       // Add a cast for x86-64.
                       name, si->name, (uint32_t)s->st_value, (int)s->st_size);
                       // ARC MOD END
            return s;
        }
    }

    return NULL;
}

static unsigned elfhash(const char* _name) {
    const unsigned char* name = (const unsigned char*) _name;
    unsigned h = 0, g;

    while(*name) {
        h = (h << 4) + *name++;
        g = h & 0xf0000000;
        h ^= g;
        h ^= g >> 24;
    }
    return h;
}

static Elf32_Sym* soinfo_do_lookup(soinfo* si, const char* name, soinfo** lsi, soinfo* needed[]) {
    unsigned elf_hash = elfhash(name);
    Elf32_Sym* s = NULL;

    if (si != NULL && somain != NULL) {

        /*
         * Local scope is executable scope. Just start looking into it right away
         * for the shortcut.
         */

        if (si == somain) {
            s = soinfo_elf_lookup(si, elf_hash, name);
            if (s != NULL) {
                *lsi = si;
                goto done;
            }
        } else {
            /* Order of symbol lookup is controlled by DT_SYMBOLIC flag */

            /*
             * If this object was built with symbolic relocations disabled, the
             * first place to look to resolve external references is the main
             * executable.
             */
            // ARC MOD BEGIN
            // For real Android apps, the main binary is app_process,
            // which has no meaningful symbol and no lookup is done
            // here. This code path would exist for non-app
            // executables. On the other hand, arc.nexe has a lot of
            // symbols. To emulate the behavior for app_process, we
            // resolve no symbol here.
            // TODO(crbug.com/368131): Add an integration test for this.
#if !defined(HAVE_ARC)
            // ARC MOD END
            if (!si->has_DT_SYMBOLIC) {
                DEBUG("%s: looking up %s in executable %s",
                      si->name, name, somain->name);
                s = soinfo_elf_lookup(somain, elf_hash, name);
                if (s != NULL) {
                    *lsi = somain;
                    goto done;
                }
            }
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            /* Look for symbols in the local scope (the object who is
             * searching). This happens with C++ templates on i386 for some
             * reason.
             *
             * Notes on weak symbols:
             * The ELF specs are ambiguous about treatment of weak definitions in
             * dynamic linking.  Some systems return the first definition found
             * and some the first non-weak definition.   This is system dependent.
             * Here we return the first definition found for simplicity.  */

            s = soinfo_elf_lookup(si, elf_hash, name);
            if (s != NULL) {
                *lsi = si;
                goto done;
            }

            /*
             * If this object was built with -Bsymbolic and symbol is not found
             * in the local scope, try to find the symbol in the main executable.
             */
            // ARC MOD BEGIN
            // See the comment for the !DT_SYMBOLIC case above.
#if !defined(HAVE_ARC)
            // ARC MOD END
            if (si->has_DT_SYMBOLIC) {
                DEBUG("%s: looking up %s in executable %s after local scope",
                      si->name, name, somain->name);
                s = soinfo_elf_lookup(somain, elf_hash, name);
                if (s != NULL) {
                    *lsi = somain;
                    goto done;
                }
            }
            // ARC MOD BEGIN
#endif
            // ARC MOD END
        }
    }

    /* Next, look for it in the preloads list */
    for (int i = 0; gLdPreloads[i] != NULL; i++) {
        s = soinfo_elf_lookup(gLdPreloads[i], elf_hash, name);
        if (s != NULL) {
            *lsi = gLdPreloads[i];
            goto done;
        }
    }

    for (int i = 0; needed[i] != NULL; i++) {
        DEBUG("%s: looking up %s in %s",
              si->name, name, needed[i]->name);
        s = soinfo_elf_lookup(needed[i], elf_hash, name);
        if (s != NULL) {
            *lsi = needed[i];
            goto done;
        }
    }

done:
    if (s != NULL) {
        TRACE_TYPE(LOOKUP, "si %s sym %s s->st_value = 0x%08x, "
                   "found in %s, base = 0x%08x, load bias = 0x%08x",
                   // ARC MOD BEGIN
                   // Add a cast for x86-64.
                   si->name, name, (uint32_t)s->st_value,
                   (*lsi)->name, (uint32_t)(*lsi)->base, (uint32_t)(*lsi)->load_bias);
                   // ARC MOD END
        return s;
    }

    return NULL;
}

/* This is used by dlsym(3).  It performs symbol lookup only within the
   specified soinfo object and not in any of its dependencies.

   TODO: Only looking in the specified soinfo seems wrong. dlsym(3) says
   that it should do a breadth first search through the dependency
   tree. This agrees with the ELF spec (aka System V Application
   Binary Interface) where in Chapter 5 it discuss resolving "Shared
   Object Dependencies" in breadth first search order.
 */
Elf32_Sym* dlsym_handle_lookup(soinfo* si, const char* name)
{
    return soinfo_elf_lookup(si, elfhash(name), name);
}

/* This is used by dlsym(3) to performs a global symbol lookup. If the
   start value is null (for RTLD_DEFAULT), the search starts at the
   beginning of the global solist. Otherwise the search starts at the
   specified soinfo (for RTLD_NEXT).
 */
Elf32_Sym* dlsym_linear_lookup(const char* name, soinfo** found, soinfo* start) {
  unsigned elf_hash = elfhash(name);

  if (start == NULL) {
    start = solist;
  }

  Elf32_Sym* s = NULL;
  for (soinfo* si = start; (s == NULL) && (si != NULL); si = si->next) {
    s = soinfo_elf_lookup(si, elf_hash, name);
    if (s != NULL) {
      *found = si;
      break;
    }
  }

  if (s != NULL) {
    TRACE_TYPE(LOOKUP, "%s s->st_value = 0x%08x, found->base = 0x%08x",
               // ARC MOD BEGIN
               // Add a cast for x86-64.
               name, (uint32_t)s->st_value, (uint32_t)(*found)->base);
               // ARC MOD END
  }

  return s;
}

soinfo* find_containing_library(const void* p) {
  Elf32_Addr address = reinterpret_cast<Elf32_Addr>(p);
  for (soinfo* si = solist; si != NULL; si = si->next) {
    if (address >= si->base && address - si->base < si->size) {
      return si;
    }
  }
  return NULL;
}

Elf32_Sym* dladdr_find_symbol(soinfo* si, const void* addr) {
  // ARC MOD BEGIN UPSTREAM bionic-fix-dladdr--main-binary
  // Use si->load_bias instead of si->base. This si->base works for
  // shared objects but does not work for the main binary. The load
  // bias of a main binary is not as same as si->base of the main
  // binary unless the binary is a PIE. For example, si->load_bias
  // of a NaCl main binary is 0 but its base is 0x10000.
  Elf32_Addr soaddr = reinterpret_cast<Elf32_Addr>(addr) - si->load_bias;
  // ARC MOD END UPSTREAM

  // Search the library's symbol table for any defined symbol which
  // contains this address.
  for (size_t i = 0; i < si->nchain; ++i) {
    Elf32_Sym* sym = &si->symtab[i];
    if (sym->st_shndx != SHN_UNDEF &&
        soaddr >= sym->st_value &&
        soaddr < sym->st_value + sym->st_size) {
      return sym;
    }
  }

  return NULL;
}

#if 0
static void dump(soinfo* si)
{
    Elf32_Sym* s = si->symtab;
    for (unsigned n = 0; n < si->nchain; n++) {
        TRACE("%04d> %08x: %02x %04x %08x %08x %s", n, s,
               s->st_info, s->st_shndx, s->st_value, s->st_size,
               si->strtab + s->st_name);
        s++;
    }
}
#endif

// ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
static int open_library_nacl(const char* name) {
  ScopedElapsedTimePrinter<__LINE__> printer(
      "Called open_library_nacl for", name);
  char buf[512];
  // Once __inject_arc_linker_hooks has been called, we only use
  // posix_translation based file descriptors, so we do not use
  // __nacl_irt_open_resource.
  if (g_resolve_symbol) {
    // If |name| contains a slash, we have already tried to open this
    // file in open_library().
    if (strchr(name, '/'))
      return -1;
    __libc_format_buffer(buf, sizeof(buf), "/system/lib/%s", name);
    return open(buf, O_RDONLY);
  } else {
    // If the name is a basename (does not start with /), prepend /lib/ to the
    // path because that is what nacl_irt_open_resource expects.
    if (name && name[0] != '/') {
      __libc_format_buffer(buf, sizeof(buf), DL_DST_LIB "/%s", name);
      name = buf;
    }
    // When the path starts with DL_DST_LIB, the file is specified by
    // NaCl's NMF, which can be accessed only by open_resource IRT
    // call. For this case, we need to call __nacl_irt_open_resource
    // without trying stat for this file.
    if (!memcmp(DL_DST_LIB "/", name, sizeof(DL_DST_LIB))) {
      int fd;
      if (__nacl_irt_open_resource(name, &fd) != 0)
        return -1;
      return fd;
    }
    return -1;
  }
}
#endif

// ARC MOD END
static int open_library_on_path(const char* name, const char* const paths[]) {
  char buf[512];
  for (size_t i = 0; paths[i] != NULL; ++i) {
    int n = __libc_format_buffer(buf, sizeof(buf), "%s/%s", paths[i], name);
    if (n < 0 || n >= static_cast<int>(sizeof(buf))) {
      PRINT("Warning: ignoring very long library path: %s/%s", paths[i], name);
      continue;
    }
    int fd = TEMP_FAILURE_RETRY(open(buf, O_RDONLY | O_CLOEXEC));
    if (fd != -1) {
      return fd;
    }
  }
  return -1;
}

static int open_library(const char* name) {
  // ARC MOD BEGIN
  // Note on which code path is used for which case:
  //
  // 1. DT_NEEDED specified by arc.nexe: We use
  //   __nacl_irt_open_resource() directly from open_library_nacl.
  // 2. dlopen for binaries in arc.nmf (e.g., libEGL_emulation.so):
  //    If a fullpath is not specified, we prepend /system/lib and
  //    call open() from open_library_nacl or open_library. As
  //    __inject_arc_linker_hooks replaces __nacl_irt_open, this is
  //    handled by posix_translation and it calls
  //    __nacl_irt_open_resource().
  // 3. dlopen for NDK binaries (NDK direct execution mode only): We
  //    call open() from open_library. This will be handled by
  //    posix_translation and PepperFileHandler handles this.
  // 4. DT_NEEDED specified by unit tests: We use open() in
  //    open_library_on_path. Note that we rely on LD_LIBRARY_PATH
  //    specified by our unit test runner.
  // 5. dlopen from unit tests: Like 4, we use open in
  //    open_library_on_path(). __inject_arc_linker_hooks has been
  //    already called so the implementation of __nacl_irt_open is
  //    hooked, but it ends up calling __real_open for unit tests.
  //
  // ARC MOD END
  TRACE("[ opening %s ]", name);

  // If the name contains a slash, we should attempt to open it directly and not search the paths.
  if (strchr(name, '/') != NULL) {
    int fd = TEMP_FAILURE_RETRY(open(name, O_RDONLY | O_CLOEXEC));
    if (fd != -1) {
      return fd;
    }
    // ...but nvidia binary blobs (at least) rely on this behavior, so fall through for now.
  }
  // ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  int naclfd = open_library_nacl(name);
  if (naclfd != -1)
    return naclfd;
  // Note: Our unit tests need open_library_on_path calls below since
  // the test binaries have DT_NEEDED entries like "libc.so" and such
  // DT_NEEDED libraries live in a path like
  // "out/target/nacl_i686_opt/lib/", not in "/lib". Also note that
  // open_library_on_path does nothing as gLdPaths is empty on
  // production ARC and therefore is fast.
  return open_library_on_path(name, gLdPaths);

  // We have already tried /system/lib by __nacl_irt_open_resource
  // (before __inject_arc_linker_hooks) or __nacl_irt_open (after
  // __inject_arc_linker_hooks, so retrying with gSoPaths does not
  // make sense for us. Not to call open_resource IRT which
  // synchronizes with the renderer, disable the slow fallback path.
#else
  // ARC MOD END
  // Otherwise we try LD_LIBRARY_PATH first, and fall back to the built-in well known paths.
  int fd = open_library_on_path(name, gLdPaths);
  if (fd == -1) {
    fd = open_library_on_path(name, gSoPaths);
  }
  return fd;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
}

static soinfo* load_library(const char* name) {
    // Open the file.
    int fd = open_library(name);
    if (fd == -1) {
        DL_ERR("library \"%s\" not found", name);
        return NULL;
    }

    // Read the ELF header and load the segments.
    ElfReader elf_reader(name, fd);
    if (!elf_reader.Load()) {
        return NULL;
    }

    const char* bname = strrchr(name, '/');
    soinfo* si = soinfo_alloc(bname ? bname + 1 : name);
    if (si == NULL) {
        return NULL;
    }
    si->base = elf_reader.load_start();
    si->size = elf_reader.load_size();
    si->load_bias = elf_reader.load_bias();
    si->flags = 0;
    si->entry = 0;
    si->dynamic = NULL;
    si->phnum = elf_reader.phdr_count();
    si->phdr = elf_reader.loaded_phdr();
    // ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
    // Linux kernel sends the entry point using AT_ENTRY, but sel_ldr
    // does not send this info. Take this occasion and fill the field.
    const Elf32_Ehdr& header = elf_reader.header();
    if (header.e_entry)
      si->entry = header.e_entry + elf_reader.load_bias();
    if (!si->phdr)
      DL_ERR("Cannot locate a program header in \"%s\".", name);
#endif
    // ARC MOD END
    return si;
}

static soinfo *find_loaded_library(const char *name)
{
    soinfo *si;
    const char *bname;

    // TODO: don't use basename only for determining libraries
    // http://code.google.com/p/android/issues/detail?id=6670

    bname = strrchr(name, '/');
    bname = bname ? bname + 1 : name;

    for (si = solist; si != NULL; si = si->next) {
        if (!strcmp(bname, si->name)) {
            return si;
        }
    }
    return NULL;
}

static soinfo* find_library_internal(const char* name) {
  if (name == NULL) {
    return somain;
  }

  soinfo* si = find_loaded_library(name);
  if (si != NULL) {
    if (si->flags & FLAG_LINKED) {
      return si;
    }
    DL_ERR("OOPS: recursive link to \"%s\"", si->name);
    return NULL;
  }

  TRACE("[ '%s' has not been loaded yet.  Locating...]", name);
  si = load_library(name);
  if (si == NULL) {
    return NULL;
  }

  // At this point we know that whatever is loaded @ base is a valid ELF
  // shared library whose segments are properly mapped in.
  TRACE("[ init_library base=0x%08x sz=0x%08x name='%s' ]",
        // ARC MOD BEGIN
        // Add a cast for x86-64.
        (uint32_t)si->base, si->size, si->name);
        // ARC MOD END

  if (!soinfo_link_image(si)) {
    // ARC MOD BEGIN
    // We do not have the size of data segments so we cannot unmap
    // data segments.
    // TODO(crbug.com/257546): Unmap data segments.
    // ARC MOD END
    munmap(reinterpret_cast<void*>(si->base), si->size);
    soinfo_free(si);
    return NULL;
  }

  return si;
}

static soinfo* find_library(const char* name) {
  soinfo* si = find_library_internal(name);
  if (si != NULL) {
    si->ref_count++;
  }
  return si;
}

static int soinfo_unload(soinfo* si) {
  // ARC MOD BEGIN
  // Temporary workaround for 4.4 debug build. It looks like
  // malloc_debug_fini() is not working as expected.
  // TODO(yusukes): Remove this.
  if (!si)
    return 0;
  // ARC MOD END
  if (si->ref_count == 1) {
    TRACE("unloading '%s'", si->name);
    si->CallDestructors();

    for (Elf32_Dyn* d = si->dynamic; d->d_tag != DT_NULL; ++d) {
      if (d->d_tag == DT_NEEDED) {
        const char* library_name = si->strtab + d->d_un.d_val;
        TRACE("%s needs to unload %s", si->name, library_name);
        soinfo_unload(find_loaded_library(library_name));
      }
    }

    // ARC MOD BEGIN
    // When NaCl is in use, the linker maps text and data separately.
    // The following code unmaps the latter.
#if defined(__native_client__)
    size_t code_first = 0;
    size_t code_size = 0;
    size_t data_first = 0;
    size_t data_size = 0;
    phdr_table_get_nacl_gapped_layout_info(si->phdr,
                                           si->phnum,
                                           &code_first,
                                           &code_size,
                                           &data_first,
                                           &data_size);
    TRACE("soinfo_unload: munmap data: %p-%p\n",
          (char *)data_first, (char *)data_first + data_size);
#if !defined(__arm__)
    // TODO(crbug.com/257546): Make this work for ARM too.
    munmap((char *)data_first, data_size);
#endif
    TRACE("soinfo_unload: munmap text: %p-%p\n",
          (char *)si->base, (char *)si->base + si->size);
#else
    TRACE("soinfo_unload: munmap: %p-%p\n",
          (char *)si->base, (char *)si->base + si->size);
#endif
    // ARC MOD END
    munmap(reinterpret_cast<void*>(si->base), si->size);
    notify_gdb_of_unload(si);
    soinfo_free(si);
    si->ref_count = 0;
  } else {
    si->ref_count--;
    TRACE("not unloading '%s', decrementing ref_count to %d", si->name, si->ref_count);
  }
  return 0;
}

void do_android_update_LD_LIBRARY_PATH(const char* ld_library_path) {
  if (!get_AT_SECURE()) {
    parse_LD_LIBRARY_PATH(ld_library_path);
  }
}

soinfo* do_dlopen(const char* name, int flags) {
  if ((flags & ~(RTLD_NOW|RTLD_LAZY|RTLD_LOCAL|RTLD_GLOBAL)) != 0) {
    DL_ERR("invalid flags to dlopen: %x", flags);
    return NULL;
  }
  set_soinfo_pool_protection(PROT_READ | PROT_WRITE);
  soinfo* si = find_library(name);
  if (si != NULL) {
    si->CallConstructors();
  }
  set_soinfo_pool_protection(PROT_READ);
  return si;
}

int do_dlclose(soinfo* si) {
  set_soinfo_pool_protection(PROT_READ | PROT_WRITE);
  int result = soinfo_unload(si);
  set_soinfo_pool_protection(PROT_READ);
  return result;
}
// ARC MOD BEGIN
// Add __inject_arc_linker_hooks and nacl_irt_open_resource_invalid.
static int nacl_irt_open_resource_invalid(const char* name, int* fd) {
  DL_ERR("We must not call __nacl_irt_open_resource after "
         "__inject_arc_linker_hooks: name=%s", name);
  exit(1);
}

void __inject_arc_linker_hooks(__arc_linker_hooks* hooks) {
  if (g_resolve_symbol) {
    DL_ERR("The linker hooks are already installed.");
    exit(-1);
  }
  if (!hooks->nacl_irt_close ||
      !hooks->nacl_irt_mmap ||
      !hooks->nacl_irt_munmap ||
      !hooks->nacl_irt_open ||
      !hooks->nacl_irt_read ||
      !hooks->nacl_irt_write ||
      !hooks->resolve_symbol) {
    DL_ERR("All fields in hooks must be filled.");
    exit(-1);
  }

  g_resolve_symbol = hooks->resolve_symbol;
  g_is_statically_linked = hooks->is_statically_linked;
  __nacl_irt_close = hooks->nacl_irt_close;
  __nacl_irt_mmap = hooks->nacl_irt_mmap;
  __nacl_irt_munmap = hooks->nacl_irt_munmap;
  __nacl_irt_open = hooks->nacl_irt_open;
  __nacl_irt_read = hooks->nacl_irt_read;
  __nacl_irt_write = hooks->nacl_irt_write;
  // We will not call __nacl_irt_open_resource in the Bionic loader
  // after this not to mix NaCl FD with posix_translation FD.
  __nacl_irt_open_resource = nacl_irt_open_resource_invalid;
}
// ARC MOD END

/* TODO: don't use unsigned for addrs below. It works, but is not
 * ideal. They should probably be either uint32_t, Elf32_Addr, or unsigned
 * long.
 */
// ARC MOD BEGIN
// System V Application Binary Interface AMD64 Architecture
// Processor Supplement says "The AMD64 ABI architectures uses
// only Elf64_Rela relocation entries with explicit addends."
// http://www.x86-64.org/documentation/abi.pdf
#if defined(ANDROID_X86_64_LINKER)
static int soinfo_relocate(soinfo *si, Elf64_Rela *rel, unsigned count,
                           soinfo *needed[])
#else
// ARC MOD END
static int soinfo_relocate(soinfo* si, Elf32_Rel* rel, unsigned count,
                           soinfo* needed[])
// ARC MOD BEGIN
#endif
// ARC MOD END
{
    Elf32_Sym* symtab = si->symtab;
    const char* strtab = si->strtab;
    // ARC MOD BEGIN
    // Initialize this by NULL.
    Elf32_Sym* s = NULL;
    // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
    Elf64_Rela *start = rel;
#else
    // ARC MOD END
    Elf32_Rel* start = rel;
    // ARC MOD BEGIN
#endif
    // Initialize |lsi| with NULL to remove GCC -O2 warnings.
    soinfo* lsi = NULL;
    // ARC MOD END

    for (size_t idx = 0; idx < count; ++idx, ++rel) {
        // ARC MOD BEGIN
        // Use ELFW(R_*) instead of ELF32_R_*.
        unsigned type = ELFW(R_TYPE)(rel->r_info);
        unsigned sym = ELFW(R_SYM)(rel->r_info);
        // ARC MOD END
        Elf32_Addr reloc = static_cast<Elf32_Addr>(rel->r_offset + si->load_bias);
        Elf32_Addr sym_addr = 0;
        char* sym_name = NULL;

        DEBUG("Processing '%s' relocation at index %d", si->name, idx);
        if (type == 0) { // R_*_NONE
            continue;
        }
        if (sym != 0) {
            sym_name = (char *)(strtab + symtab[sym].st_name);
            // ARC MOD BEGIN
            // We must not look up local symbols. RESOLVE_MAP in
            // nacl-glibc/elf/dl-reloc.c handles local symbols similarly.
            //
            // We treat all symbols in the Bionic loader as
            // local. When we are relocating the Bionic loader, it
            // cannot use lookup() because libdl_info in dlfcn.c is
            // not relocated yet. Upstream Bionic may not have this
            // issue because it uses RTLD_LOCAL semantics.
            //
            // We also modified code in else clause for ARC. See the
            // comment in the else clause for detail.
            if(ELFW(ST_BIND)(symtab[sym].st_info) == STB_LOCAL ||
               // TODO(yusukes): Check if this is still necessary.
               (si->flags & FLAG_LINKER) == FLAG_LINKER) {
              s = &symtab[sym];
              lsi = si;
            } else {
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
              // If |g_resolve_symbol| is injected, try this first.
              if (g_resolve_symbol) {
                  sym_addr = reinterpret_cast<Elf32_Addr>(
                      g_resolve_symbol(sym_name));
                  if (sym_addr) {
                      goto symbol_found;
                  }
              }

              // Then look up the symbol following Android's default
              // semantics.
              s = soinfo_do_lookup(si, sym_name, &lsi, needed);
              // When the symbol is not found, we still need to
              // look up the main binary, as we link some shared
              // objects (e.g., liblog.so) into arc.nexe
              // TODO(crbug.com/400947): Remove this code once we have
              // stopped converting .so files to .a.
              if (!s)
                  s = soinfo_do_lookup(somain, sym_name, &lsi, needed);
#else
              s = soinfo_do_lookup(si, sym_name, &lsi, needed);
#endif
            }
            // ARC MOD END
            if (s == NULL) {
                /* We only allow an undefined symbol if this is a weak
                   reference..   */
                s = &symtab[sym];
                // ARC MOD BEGIN
                // Use ELFW(ST_BIND) instead of ELF32_ST_BIND.
                if (ELFW(ST_BIND)(s->st_info) != STB_WEAK) {
                // ARC MOD END
                    DL_ERR("cannot locate symbol \"%s\" referenced by \"%s\"...", sym_name, si->name);
                    return -1;
                }

                /* IHI0044C AAELF 4.5.1.1:

                   Libraries are not searched to resolve weak references.
                   It is not an error for a weak reference to remain
                   unsatisfied.

                   During linking, the value of an undefined weak reference is:
                   - Zero if the relocation type is absolute
                   - The address of the place if the relocation is pc-relative
                   - The address of nominal base address if the relocation
                     type is base-relative.
                  */

                switch (type) {
#if defined(ANDROID_ARM_LINKER)
                case R_ARM_JUMP_SLOT:
                case R_ARM_GLOB_DAT:
                case R_ARM_ABS32:
                case R_ARM_RELATIVE:    /* Don't care. */
#elif defined(ANDROID_X86_LINKER)
                case R_386_JMP_SLOT:
                case R_386_GLOB_DAT:
                case R_386_32:
                case R_386_RELATIVE:    /* Dont' care. */
                // ARC MOD BEGIN
                // Add cases for x86-64.
#elif defined(ANDROID_X86_64_LINKER)
                case R_X86_64_JMP_SLOT:
                case R_X86_64_GLOB_DAT:
                case R_X86_64_32:
                case R_X86_64_64:
                case R_X86_64_RELATIVE:    /* Don't care. */
                // ARC MOD END
#endif /* ANDROID_*_LINKER */
                    /* sym_addr was initialized to be zero above or relocation
                       code below does not care about value of sym_addr.
                       No need to do anything.  */
                    break;

#if defined(ANDROID_X86_LINKER)
                case R_386_PC32:
                    sym_addr = reloc;
                    break;
                // ARC MOD BEGIN
                // Add a case for x86-64.
#if defined(ANDROID_X86_64_LINKER)
                case R_X86_64_PC32:
                    sym_addr = reloc;
                    break;
#endif /* ANDROID_X86_64_LINKER */
                // ARC MOD END
#endif /* ANDROID_X86_LINKER */

#if defined(ANDROID_ARM_LINKER)
                case R_ARM_COPY:
                    /* Fall through.  Can't really copy if weak symbol is
                       not found in run-time.  */
#endif /* ANDROID_ARM_LINKER */
                default:
                    DL_ERR("unknown weak reloc type %d @ %p (%d)",
                                 type, rel, (int) (rel - start));
                    return -1;
                }
            } else {
                /* We got a definition.  */
#if 0
                if ((base == 0) && (si->base != 0)) {
                        /* linking from libraries to main image is bad */
                    DL_ERR("cannot locate \"%s\"...",
                           strtab + symtab[sym].st_name);
                    return -1;
                }
#endif
                sym_addr = static_cast<Elf32_Addr>(s->st_value + lsi->load_bias);
            }
            // ARC MOD BEGIN
            // Add symbol_found label.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
        symbol_found:
#endif
            // ARC MOD END
            count_relocation(kRelocSymbol);
        } else {
            s = NULL;
        }
        // ARC MOD BEGIN
        // In x86-64, rel is Elf64_Rela and we have to add r_addend.
#if defined(ANDROID_X86_64_LINKER)
        sym_addr += rel->r_addend;
#endif
        // ARC MOD END

/* TODO: This is ugly. Split up the relocations by arch into
 * different files.
 */
        switch(type){
#if defined(ANDROID_ARM_LINKER)
        case R_ARM_JUMP_SLOT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO JMP_SLOT %08x <- %08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        case R_ARM_GLOB_DAT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO GLOB_DAT %08x <- %08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        case R_ARM_ABS32:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO ABS %08x <- %08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += sym_addr;
            break;
        case R_ARM_REL32:
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO REL32 %08x <- %08x - %08x %s",
                       reloc, sym_addr, rel->r_offset, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += sym_addr - rel->r_offset;
            break;
#elif defined(ANDROID_X86_LINKER)
        case R_386_JMP_SLOT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO JMP_SLOT %08x <- %08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        case R_386_GLOB_DAT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO GLOB_DAT %08x <- %08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        // ARC MOD BEGIN
        // Add cases for x86-64. Their implementations are almost the
        // same as the cases for x86.
#elif defined(ANDROID_X86_64_LINKER)
        case R_X86_64_JMP_SLOT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO JMP_SLOT %08llx <- %08llx %s",
                       reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        case R_X86_64_GLOB_DAT:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO GLOB_DAT %08llx <- %08llx %s",
                       reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) = sym_addr;
            break;
        // ARC MOD END
#elif defined(ANDROID_MIPS_LINKER)
    case R_MIPS_REL32:
            count_relocation(kRelocAbsolute);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO REL32 %08x <- %08x %s",
                       reloc, sym_addr, (sym_name) ? sym_name : "*SECTIONHDR*");
            if (s) {
                *reinterpret_cast<Elf32_Addr*>(reloc) += sym_addr;
            } else {
                *reinterpret_cast<Elf32_Addr*>(reloc) += si->base;
            }
            break;
#endif /* ANDROID_*_LINKER */

#if defined(ANDROID_ARM_LINKER)
        case R_ARM_RELATIVE:
#elif defined(ANDROID_X86_LINKER)
        case R_386_RELATIVE:
        // ARC MOD BEGIN
        // Add a case for x86-64.
#elif defined(ANDROID_X86_64_LINKER)
        case R_X86_64_RELATIVE:
        // ARC MOD END
#endif /* ANDROID_*_LINKER */
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);
            if (sym) {
                DL_ERR("odd RELATIVE form...");
                return -1;
            }
            // ARC MOD BEGIN
            // Add a cast for x86-64.
            TRACE_TYPE(RELO, "RELO RELATIVE %08x <- +%08x", (uint32_t)reloc, (uint32_t)si->base);
            // ARC MOD END
            *reinterpret_cast<Elf32_Addr*>(reloc) += si->base;
            break;

#if defined(ANDROID_X86_LINKER)
        case R_386_32:
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);

            TRACE_TYPE(RELO, "RELO R_386_32 %08x <- +%08x %s", reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += sym_addr;
            break;

        case R_386_PC32:
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO R_386_PC32 %08x <- +%08x (%08x - %08x) %s",
                       reloc, (sym_addr - reloc), sym_addr, reloc, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += (sym_addr - reloc);
            break;
#endif /* ANDROID_X86_LINKER */

        // ARC MOD BEGIN
        // Add cases for x86-64. Their implementations are almost the
        // same as the cases for x86.
#if defined(ANDROID_X86_64_LINKER)
        case R_X86_64_32:
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO R_X86_64_32 %08llx <- +%08llx %s",
                       reloc, sym_addr, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += sym_addr;
            break;

        case R_X86_64_PC32:
            count_relocation(kRelocRelative);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO R_X86_64_PC32 %08llx <- "
                       "+%08llx (%08llx - %08llx) %s", reloc,
                       (sym_addr - reloc), sym_addr, reloc, sym_name);
            *reinterpret_cast<Elf32_Addr*>(reloc) += (sym_addr - reloc);
            break;
#endif /* ANDROID_X86_64_LINKER */
        // ARC MOD END
#ifdef ANDROID_ARM_LINKER
        case R_ARM_COPY:
            if ((si->flags & FLAG_EXE) == 0) {
                /*
                 * http://infocenter.arm.com/help/topic/com.arm.doc.ihi0044d/IHI0044D_aaelf.pdf
                 *
                 * Section 4.7.1.10 "Dynamic relocations"
                 * R_ARM_COPY may only appear in executable objects where e_type is
                 * set to ET_EXEC.
                 *
                 * TODO: FLAG_EXE is set for both ET_DYN and ET_EXEC executables.
                 * We should explicitly disallow ET_DYN executables from having
                 * R_ARM_COPY relocations.
                 */
                DL_ERR("%s R_ARM_COPY relocations only supported for ET_EXEC", si->name);
                return -1;
            }
            count_relocation(kRelocCopy);
            MARK(rel->r_offset);
            TRACE_TYPE(RELO, "RELO %08x <- %d @ %08x %s", reloc, s->st_size, sym_addr, sym_name);
            if (reloc == sym_addr) {
                Elf32_Sym *src = soinfo_do_lookup(NULL, sym_name, &lsi, needed);

                if (src == NULL) {
                    DL_ERR("%s R_ARM_COPY relocation source cannot be resolved", si->name);
                    return -1;
                }
                if (lsi->has_DT_SYMBOLIC) {
                    DL_ERR("%s invalid R_ARM_COPY relocation against DT_SYMBOLIC shared "
                           "library %s (built with -Bsymbolic?)", si->name, lsi->name);
                    return -1;
                }
                if (s->st_size < src->st_size) {
                    DL_ERR("%s R_ARM_COPY relocation size mismatch (%d < %d)",
                           si->name, s->st_size, src->st_size);
                    return -1;
                }
                memcpy((void*)reloc, (void*)(src->st_value + lsi->load_bias), src->st_size);
            } else {
                DL_ERR("%s R_ARM_COPY relocation target cannot be resolved", si->name);
                return -1;
            }
            break;
#endif /* ANDROID_ARM_LINKER */

        default:
            DL_ERR("unknown reloc type %d @ %p (%d)",
                   type, rel, (int) (rel - start));
            return -1;
        }
    }
    return 0;
}

#ifdef ANDROID_MIPS_LINKER
static bool mips_relocate_got(soinfo* si, soinfo* needed[]) {
    unsigned* got = si->plt_got;
    if (got == NULL) {
        return true;
    }
    unsigned local_gotno = si->mips_local_gotno;
    unsigned gotsym = si->mips_gotsym;
    unsigned symtabno = si->mips_symtabno;
    Elf32_Sym* symtab = si->symtab;

    /*
     * got[0] is address of lazy resolver function
     * got[1] may be used for a GNU extension
     * set it to a recognizable address in case someone calls it
     * (should be _rtld_bind_start)
     * FIXME: maybe this should be in a separate routine
     */

    if ((si->flags & FLAG_LINKER) == 0) {
        size_t g = 0;
        got[g++] = 0xdeadbeef;
        if (got[g] & 0x80000000) {
            got[g++] = 0xdeadfeed;
        }
        /*
         * Relocate the local GOT entries need to be relocated
         */
        for (; g < local_gotno; g++) {
            got[g] += si->load_bias;
        }
    }

    /* Now for the global GOT entries */
    Elf32_Sym* sym = symtab + gotsym;
    got = si->plt_got + local_gotno;
    for (size_t g = gotsym; g < symtabno; g++, sym++, got++) {
        const char* sym_name;
        Elf32_Sym* s;
        soinfo* lsi;

        /* This is an undefined reference... try to locate it */
        sym_name = si->strtab + sym->st_name;
        s = soinfo_do_lookup(si, sym_name, &lsi, needed);
        if (s == NULL) {
            /* We only allow an undefined symbol if this is a weak
               reference..   */
            s = &symtab[g];
            if (ELF32_ST_BIND(s->st_info) != STB_WEAK) {
                DL_ERR("cannot locate \"%s\"...", sym_name);
                return false;
            }
            *got = 0;
        }
        else {
            /* FIXME: is this sufficient?
             * For reference see NetBSD link loader
             * http://cvsweb.netbsd.org/bsdweb.cgi/src/libexec/ld.elf_so/arch/mips/mips_reloc.c?rev=1.53&content-type=text/x-cvsweb-markup
             */
             *got = lsi->load_bias + s->st_value;
        }
    }
    return true;
}
#endif

void soinfo::CallArray(const char* array_name UNUSED, linker_function_t* functions, size_t count, bool reverse) {
  if (functions == NULL) {
    return;
  }

  TRACE("[ Calling %s (size %d) @ %p for '%s' ]", array_name, count, functions, name);

  int begin = reverse ? (count - 1) : 0;
  int end = reverse ? -1 : count;
  int step = reverse ? -1 : 1;

  for (int i = begin; i != end; i += step) {
    TRACE("[ %s[%d] == %p ]", array_name, i, functions[i]);
    // ARC MOD BEGIN
    // The loader passes __nacl_irt_query to the main executable
    // using the function in init_array of libc.so. The loader
    // does this only for the function immediately after the magic
    // number. Currently, init_array is used only on ARM. We use
    // .init in other platforms. See bionic/linker/linker.h for
    // why we need to pass __nacl_irt_query in this way.
    if (!reverse && functions[i] == NEXT_CTOR_FUNC_NEEDS_IRT_QUERY_MARKER) {
      TRACE("[ Calling func @ 0x%08x with __nacl_irt_query]\n",
            (unsigned)functions[i]);
      ((void (*)(__nacl_irt_query_fn_t))functions[++i])(__nacl_irt_query);
    } else
    // ARC MOD END
    CallFunction("function", functions[i]);
  }

  TRACE("[ Done calling %s for '%s' ]", array_name, name);
}

void soinfo::CallFunction(const char* function_name UNUSED, linker_function_t function) {
  if (function == NULL || reinterpret_cast<uintptr_t>(function) == static_cast<uintptr_t>(-1)) {
    return;
  }

  TRACE("[ Calling %s @ %p for '%s' ]", function_name, function, name);
  function();
  TRACE("[ Done calling %s @ %p for '%s' ]", function_name, function, name);

  // The function may have called dlopen(3) or dlclose(3), so we need to ensure our data structures
  // are still writable. This happens with our debug malloc (see http://b/7941716).
  set_soinfo_pool_protection(PROT_READ | PROT_WRITE);
}

void soinfo::CallPreInitConstructors() {
  // DT_PREINIT_ARRAY functions are called before any other constructors for executables,
  // but ignored in a shared library.
  CallArray("DT_PREINIT_ARRAY", preinit_array, preinit_array_count, false);
}

void soinfo::CallConstructors() {
  if (constructors_called) {
    return;
  }

  // We set constructors_called before actually calling the constructors, otherwise it doesn't
  // protect against recursive constructor calls. One simple example of constructor recursion
  // is the libc debug malloc, which is implemented in libc_malloc_debug_leak.so:
  // 1. The program depends on libc, so libc's constructor is called here.
  // 2. The libc constructor calls dlopen() to load libc_malloc_debug_leak.so.
  // 3. dlopen() calls the constructors on the newly created
  //    soinfo for libc_malloc_debug_leak.so.
  // 4. The debug .so depends on libc, so CallConstructors is
  //    called again with the libc soinfo. If it doesn't trigger the early-
  //    out above, the libc constructor will be called again (recursively!).
  constructors_called = true;

  // ARC MOD BEGIN
  // Print the elapsed time for calling init functions.
  ScopedElapsedTimePrinter<__LINE__> printer("Called constructors for", name);
  // ARC MOD END
  if ((flags & FLAG_EXE) == 0 && preinit_array != NULL) {
    // The GNU dynamic linker silently ignores these, but we warn the developer.
    PRINT("\"%s\": ignoring %d-entry DT_PREINIT_ARRAY in shared library!",
          name, preinit_array_count);
  }

  if (dynamic != NULL) {
    for (Elf32_Dyn* d = dynamic; d->d_tag != DT_NULL; ++d) {
      if (d->d_tag == DT_NEEDED) {
        const char* library_name = strtab + d->d_un.d_val;
        TRACE("\"%s\": calling constructors in DT_NEEDED \"%s\"", name, library_name);
        // ARC MOD BEGIN
        // We may not be able to find DT_NEEDED specified by NDK's
        // shared objects, because ARC links a lot of libraries to
        // the main binary. For example, NDK apps may have DT_NEEDED
        // which expects libz.so exists, but ARC does not have
        // libz.so. We build libz.a and link it to the main binary.
        //
        // For such DT_NEEDED in NDK objects, find_loaded_library()
        // may return NULL. We must not try calling CallConstructors()
        // for them.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
        if (g_resolve_symbol) {
          soinfo* si = find_loaded_library(library_name);
          if (si)
            si->CallConstructors();
        } else
#endif
        // ARC MOD END
        find_loaded_library(library_name)->CallConstructors();
      }
    }
  }

  TRACE("\"%s\": calling constructors", name);

  // DT_INIT should be called before DT_INIT_ARRAY if both are present.
  // ARC MOD BEGIN
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  // The loader passes __nacl_irt_query to the main executable
  // here. See bionic/linker/linker.h for detail.
  if (init_func != NULL &&
      reinterpret_cast<uintptr_t>(init_func) != static_cast<uintptr_t>(-1)) {
    init_func(__nacl_irt_query);
    set_soinfo_pool_protection(PROT_READ | PROT_WRITE);
  }
#else
  // ARC MOD END
  CallFunction("DT_INIT", init_func);
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  CallArray("DT_INIT_ARRAY", init_array, init_array_count, false);
}

void soinfo::CallDestructors() {
  TRACE("\"%s\": calling destructors", name);

  // DT_FINI_ARRAY must be parsed in reverse order.
  CallArray("DT_FINI_ARRAY", fini_array, fini_array_count, true);

  // DT_FINI should be called after DT_FINI_ARRAY if both are present.
  CallFunction("DT_FINI", fini_func);
}

/* Force any of the closed stdin, stdout and stderr to be associated with
   /dev/null. */
static int nullify_closed_stdio() {
    int dev_null, i, status;
    int return_value = 0;

    dev_null = TEMP_FAILURE_RETRY(open("/dev/null", O_RDWR));
    if (dev_null < 0) {
        DL_ERR("cannot open /dev/null: %s", strerror(errno));
        return -1;
    }
    TRACE("[ Opened /dev/null file-descriptor=%d]", dev_null);

    /* If any of the stdio file descriptors is valid and not associated
       with /dev/null, dup /dev/null to it.  */
    for (i = 0; i < 3; i++) {
        /* If it is /dev/null already, we are done. */
        if (i == dev_null) {
            continue;
        }

        TRACE("[ Nullifying stdio file descriptor %d]", i);
        status = TEMP_FAILURE_RETRY(fcntl(i, F_GETFL));

        /* If file is opened, we are good. */
        if (status != -1) {
            continue;
        }

        /* The only error we allow is that the file descriptor does not
           exist, in which case we dup /dev/null to it. */
        if (errno != EBADF) {
            DL_ERR("fcntl failed: %s", strerror(errno));
            return_value = -1;
            continue;
        }

        /* Try dupping /dev/null to this stdio file descriptor and
           repeat if there is a signal.  Note that any errors in closing
           the stdio descriptor are lost.  */
        status = TEMP_FAILURE_RETRY(dup2(dev_null, i));
        if (status < 0) {
            DL_ERR("dup2 failed: %s", strerror(errno));
            return_value = -1;
            continue;
        }
    }

    /* If /dev/null is not one of the stdio file descriptors, close it. */
    if (dev_null > 2) {
        TRACE("[ Closing /dev/null file-descriptor=%d]", dev_null);
        status = TEMP_FAILURE_RETRY(close(dev_null));
        if (status == -1) {
            DL_ERR("close failed: %s", strerror(errno));
            return_value = -1;
        }
    }

    return return_value;
}

static bool soinfo_link_image(soinfo* si) {
    /* "base" might wrap around UINT32_MAX. */
    Elf32_Addr base = si->load_bias;
    const Elf32_Phdr *phdr = si->phdr;
    int phnum = si->phnum;
    bool relocating_linker = (si->flags & FLAG_LINKER) != 0;

    /* We can't debug anything until the linker is relocated */
    if (!relocating_linker) {
        INFO("[ linking %s ]", si->name);
        // ARC MOD BEGIN
        // Add a cast for x86-64.
        DEBUG("si->base = 0x%08x si->flags = 0x%08x", (uint32_t)si->base, si->flags);
        // ARC MOD END
    }

    /* Extract dynamic section */
    size_t dynamic_count;
    Elf32_Word dynamic_flags;
    phdr_table_get_dynamic_section(phdr, phnum, base, &si->dynamic,
                                   &dynamic_count, &dynamic_flags);
    if (si->dynamic == NULL) {
        if (!relocating_linker) {
            DL_ERR("missing PT_DYNAMIC in \"%s\"", si->name);
        }
        return false;
    } else {
        if (!relocating_linker) {
            DEBUG("dynamic = %p", si->dynamic);
        }
    }
    // ARC MOD BEGIN UPSTREAM bionic-set-l_ld-in-main-binary
    if (si->flags & FLAG_EXE)
        si->link_map.l_ld = (uintptr_t)si->dynamic;
    // ARC MOD END UPSTREAM

#ifdef ANDROID_ARM_LINKER
    (void) phdr_table_get_arm_exidx(phdr, phnum, base,
                                    &si->ARM_exidx, &si->ARM_exidx_count);
#endif

    // Extract useful information from dynamic section.
    uint32_t needed_count = 0;
    for (Elf32_Dyn* d = si->dynamic; d->d_tag != DT_NULL; ++d) {
        // ARC MOD BEGIN
        // Add a cast for x86-64.
        DEBUG("d = %p, d[0](tag) = 0x%08x d[1](val) = 0x%08x", d,
              (uint32_t)d->d_tag, (uint32_t)d->d_un.d_val);
        // ARC MOD END
        switch(d->d_tag){
        case DT_HASH:
            si->nbucket = ((unsigned *) (base + d->d_un.d_ptr))[0];
            si->nchain = ((unsigned *) (base + d->d_un.d_ptr))[1];
            si->bucket = (unsigned *) (base + d->d_un.d_ptr + 8);
            si->chain = (unsigned *) (base + d->d_un.d_ptr + 8 + si->nbucket * 4);
            break;
        case DT_STRTAB:
            si->strtab = (const char *) (base + d->d_un.d_ptr);
            break;
        case DT_SYMTAB:
            si->symtab = (Elf32_Sym *) (base + d->d_un.d_ptr);
            break;
        case DT_PLTREL:
            // ARC MOD BEGIN
            // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
            if (d->d_un.d_val != DT_RELA) {
                DL_ERR("unsupported DT_REL in \"%s\"", si->name);
                return false;
            }
#else
            // ARC MOD END
            if (d->d_un.d_val != DT_REL) {
                DL_ERR("unsupported DT_RELA in \"%s\"", si->name);
                return false;
            }
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            break;
        case DT_JMPREL:
            // ARC MOD BEGIN
            // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
            si->plt_rel = (Elf64_Rela*) (base + d->d_un.d_ptr);
#else
            // ARC MOD END
            si->plt_rel = (Elf32_Rel*) (base + d->d_un.d_ptr);
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            break;
        case DT_PLTRELSZ:
            // ARC MOD BEGIN
            // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
            si->plt_rel_count = d->d_un.d_val / sizeof(Elf64_Rela);
#else
            // ARC MOD END
            si->plt_rel_count = d->d_un.d_val / sizeof(Elf32_Rel);
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            break;
        case DT_REL:
            // ARC MOD BEGIN
            // We expect Elf32_Rel (not Elf32_Rela) on 32bit CPU.
#if defined(ANDROID_X86_64_LINKER)
            DL_ERR("DT_REL not supported on 64bit");
            return false;
#else
            // ARC MOD END
            si->rel = (Elf32_Rel*) (base + d->d_un.d_ptr);
            break;
            // ARC MOD BEGIN
#endif
            // ARC MOD END
        case DT_RELSZ:
            // ARC MOD BEGIN
            // We use RELASZ instead of RELSZ on x86-64.
#if defined(ANDROID_X86_64_LINKER)
        case DT_RELASZ:
#endif
            // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
            si->rel_count = d->d_un.d_val / sizeof(Elf64_Rela);
#else
            // ARC MOD END
            si->rel_count = d->d_un.d_val / sizeof(Elf32_Rel);
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            break;
        case DT_PLTGOT:
            /* Save this in case we decide to do lazy binding. We don't yet. */
            si->plt_got = (unsigned *)(base + d->d_un.d_ptr);
            break;
        case DT_DEBUG:
            // Set the DT_DEBUG entry to the address of _r_debug for GDB
            // if the dynamic table is writable
            if ((dynamic_flags & PF_W) != 0) {
                d->d_un.d_val = (int) &_r_debug;
            }
            break;
         case DT_RELA:
            // ARC MOD BEGIN
#if defined(ANDROID_X86_64_LINKER)
            si->rel = (Elf64_Rela*) (base + d->d_un.d_ptr);
            break;
#else
            // ARC MOD END
            DL_ERR("unsupported DT_RELA in \"%s\"", si->name);
            return false;
            // ARC MOD BEGIN
#endif
            // ARC MOD END
        case DT_INIT:
            // ARC MOD BEGIN
            // The type of si->init_func was changed. See
            // bionic/linker/linker.h for detail.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
            si->init_func = (void (*)(__nacl_irt_query_fn_t))(base + d->d_un.d_ptr);
#else
            // ARC MOD END
            si->init_func = reinterpret_cast<linker_function_t>(base + d->d_un.d_ptr);
            // ARC MOD BEGIN
#endif
            // ARC MOD END
            DEBUG("%s constructors (DT_INIT) found at %p", si->name, si->init_func);
            break;
        case DT_FINI:
            si->fini_func = reinterpret_cast<linker_function_t>(base + d->d_un.d_ptr);
            DEBUG("%s destructors (DT_FINI) found at %p", si->name, si->fini_func);
            break;
        case DT_INIT_ARRAY:
            si->init_array = reinterpret_cast<linker_function_t*>(base + d->d_un.d_ptr);
            DEBUG("%s constructors (DT_INIT_ARRAY) found at %p", si->name, si->init_array);
            break;
        case DT_INIT_ARRAYSZ:
            si->init_array_count = ((unsigned)d->d_un.d_val) / sizeof(Elf32_Addr);
            break;
        case DT_FINI_ARRAY:
            si->fini_array = reinterpret_cast<linker_function_t*>(base + d->d_un.d_ptr);
            DEBUG("%s destructors (DT_FINI_ARRAY) found at %p", si->name, si->fini_array);
            break;
        case DT_FINI_ARRAYSZ:
            si->fini_array_count = ((unsigned)d->d_un.d_val) / sizeof(Elf32_Addr);
            break;
        case DT_PREINIT_ARRAY:
            si->preinit_array = reinterpret_cast<linker_function_t*>(base + d->d_un.d_ptr);
            DEBUG("%s constructors (DT_PREINIT_ARRAY) found at %p", si->name, si->preinit_array);
            break;
        case DT_PREINIT_ARRAYSZ:
            si->preinit_array_count = ((unsigned)d->d_un.d_val) / sizeof(Elf32_Addr);
            break;
        case DT_TEXTREL:
            si->has_text_relocations = true;
            break;
        case DT_SYMBOLIC:
            si->has_DT_SYMBOLIC = true;
            break;
        case DT_NEEDED:
            ++needed_count;
            break;
#if defined DT_FLAGS
        // TODO: why is DT_FLAGS not defined?
        case DT_FLAGS:
            if (d->d_un.d_val & DF_TEXTREL) {
                si->has_text_relocations = true;
            }
            if (d->d_un.d_val & DF_SYMBOLIC) {
                si->has_DT_SYMBOLIC = true;
            }
            break;
#endif
#if defined(ANDROID_MIPS_LINKER)
        case DT_STRSZ:
        case DT_SYMENT:
        case DT_RELENT:
             break;
        case DT_MIPS_RLD_MAP:
            // Set the DT_MIPS_RLD_MAP entry to the address of _r_debug for GDB.
            {
              r_debug** dp = (r_debug**) d->d_un.d_ptr;
              *dp = &_r_debug;
            }
            break;
        case DT_MIPS_RLD_VERSION:
        case DT_MIPS_FLAGS:
        case DT_MIPS_BASE_ADDRESS:
        case DT_MIPS_UNREFEXTNO:
            break;

        case DT_MIPS_SYMTABNO:
            si->mips_symtabno = d->d_un.d_val;
            break;

        case DT_MIPS_LOCAL_GOTNO:
            si->mips_local_gotno = d->d_un.d_val;
            break;

        case DT_MIPS_GOTSYM:
            si->mips_gotsym = d->d_un.d_val;
            break;

        default:
            DEBUG("Unused DT entry: type 0x%08x arg 0x%08x", d->d_tag, d->d_un.d_val);
            break;
#endif
        }
    }

    DEBUG("si->base = 0x%08x, si->strtab = %p, si->symtab = %p",
          // ARC MOD BEGIN
          // Add a cast for x86-64.
          (uint32_t)si->base, si->strtab, si->symtab);
          // ARC MOD END

    // Sanity checks.
    if (relocating_linker && needed_count != 0) {
        DL_ERR("linker cannot have DT_NEEDED dependencies on other libraries");
        return false;
    }
    if (si->nbucket == 0) {
        DL_ERR("empty/missing DT_HASH in \"%s\" (built with --hash-style=gnu?)", si->name);
        return false;
    }
    if (si->strtab == 0) {
        DL_ERR("empty/missing DT_STRTAB in \"%s\"", si->name);
        return false;
    }
    if (si->symtab == 0) {
        DL_ERR("empty/missing DT_SYMTAB in \"%s\"", si->name);
        return false;
    }

    // If this is the main executable, then load all of the libraries from LD_PRELOAD now.
    if (si->flags & FLAG_EXE) {
        memset(gLdPreloads, 0, sizeof(gLdPreloads));
        size_t preload_count = 0;
        for (size_t i = 0; gLdPreloadNames[i] != NULL; i++) {
            soinfo* lsi = find_library(gLdPreloadNames[i]);
            if (lsi != NULL) {
                gLdPreloads[preload_count++] = lsi;
            } else {
                // As with glibc, failure to load an LD_PRELOAD library is just a warning.
                DL_WARN("could not load library \"%s\" from LD_PRELOAD for \"%s\"; caused by %s",
                        gLdPreloadNames[i], si->name, linker_get_error_buffer());
            }
        }
    }

    soinfo** needed = (soinfo**) alloca((1 + needed_count) * sizeof(soinfo*));
    soinfo** pneeded = needed;

    for (Elf32_Dyn* d = si->dynamic; d->d_tag != DT_NULL; ++d) {
        if (d->d_tag == DT_NEEDED) {
            const char* library_name = si->strtab + d->d_un.d_val;
            DEBUG("%s needs %s", si->name, library_name);
            // ARC MOD BEGIN
            // We may not be able to find DT_NEEDED specified by NDK's
            // shared objects, because ARC links a lot of libraries to
            // the main binary. For example, NDK apps may have
            // DT_NEEDED which expects libz.so exists, but ARC does
            // not have libz.so. We build libz.a and link it to the
            // main binary.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
            if (g_is_statically_linked && g_is_statically_linked(library_name))
              continue;
#endif
            // ARC MOD END
            soinfo* lsi = find_library(library_name);
            if (lsi == NULL) {
                strlcpy(tmp_err_buf, linker_get_error_buffer(), sizeof(tmp_err_buf));
                DL_ERR("could not load library \"%s\" needed by \"%s\"; caused by %s",
                       library_name, si->name, tmp_err_buf);
                return false;
            }
            *pneeded++ = lsi;
        }
    }
    *pneeded = NULL;

    if (si->has_text_relocations) {
        /* Unprotect the segments, i.e. make them writable, to allow
         * text relocations to work properly. We will later call
         * phdr_table_protect_segments() after all of them are applied
         * and all constructors are run.
         */
        DL_WARN("%s has text relocations. This is wasting memory and is "
                "a security risk. Please fix.", si->name);
        if (phdr_table_unprotect_segments(si->phdr, si->phnum, si->load_bias) < 0) {
            DL_ERR("can't unprotect loadable segments for \"%s\": %s",
                   si->name, strerror(errno));
            return false;
        }
    }

    if (si->plt_rel != NULL) {
        // ARC MOD BEGIN
        // Print the elapsed time for relocating symbols.
        ScopedElapsedTimePrinter<__LINE__> printer("Relocated plt symbols for", si->name);
        // ARC MOD END
        DEBUG("[ relocating %s plt ]", si->name );
        if (soinfo_relocate(si, si->plt_rel, si->plt_rel_count, needed)) {
            return false;
        }
    }
    if (si->rel != NULL) {
        // ARC MOD BEGIN
        // Print the elapsed time for relocating symbols.
        ScopedElapsedTimePrinter<__LINE__> printer("Relocated symbols for", si->name);
        // ARC MOD END
        DEBUG("[ relocating %s ]", si->name );
        if (soinfo_relocate(si, si->rel, si->rel_count, needed)) {
            return false;
        }
    }

#ifdef ANDROID_MIPS_LINKER
    if (!mips_relocate_got(si, needed)) {
        return false;
    }
#endif

    si->flags |= FLAG_LINKED;
    DEBUG("[ finished linking %s ]", si->name);

    if (si->has_text_relocations) {
        /* All relocations are done, we can protect our segments back to
         * read-only. */
        if (phdr_table_protect_segments(si->phdr, si->phnum, si->load_bias) < 0) {
            DL_ERR("can't protect segments for \"%s\": %s",
                   si->name, strerror(errno));
            return false;
        }
    }

    /* We can also turn on GNU RELRO protection */
    if (phdr_table_protect_gnu_relro(si->phdr, si->phnum, si->load_bias) < 0) {
        DL_ERR("can't enable GNU RELRO protection for \"%s\": %s",
               si->name, strerror(errno));
        return false;
    }

    notify_gdb_of_load(si);
    return true;
}

/*
 * This function add vdso to internal dso list.
 * It helps to stack unwinding through signal handlers.
 * Also, it makes bionic more like glibc.
 */
static void add_vdso(KernelArgumentBlock& args UNUSED) {
#ifdef AT_SYSINFO_EHDR
    Elf32_Ehdr* ehdr_vdso = reinterpret_cast<Elf32_Ehdr*>(args.getauxval(AT_SYSINFO_EHDR));

    soinfo* si = soinfo_alloc("[vdso]");
    si->phdr = reinterpret_cast<Elf32_Phdr*>(reinterpret_cast<char*>(ehdr_vdso) + ehdr_vdso->e_phoff);
    si->phnum = ehdr_vdso->e_phnum;
    si->link_map.l_name = si->name;
    for (size_t i = 0; i < si->phnum; ++i) {
        if (si->phdr[i].p_type == PT_LOAD) {
            si->link_map.l_addr = reinterpret_cast<Elf32_Addr>(ehdr_vdso) - si->phdr[i].p_vaddr;
            break;
        }
    }
#endif
}

/*
 * This code is called after the linker has linked itself and
 * fixed it's own GOT. It is safe to make references to externs
 * and other non-local data at this point.
 */
static Elf32_Addr __linker_init_post_relocation(KernelArgumentBlock& args, Elf32_Addr linker_base) {
    /* NOTE: we store the args pointer on a special location
     *       of the temporary TLS area in order to pass it to
     *       the C Library's runtime initializer.
     *
     *       The initializer must clear the slot and reset the TLS
     *       to point to a different location to ensure that no other
     *       shared library constructor can access it.
     */
  __libc_init_tls(args);
  // ARC MOD BEGIN
  // Temporary support of GDB.
#if defined(BARE_METAL_BIONIC)
  // Wait for gdb attaching to this process by busy loop. If
  // __bare_metal_irt_notify_gdb_of_libraries exists, the Bionic
  // loader is launched by bare_metal_loader and not by nacl_helper,
  // so we should not wait. Note that run_under_gdb.py does not rely
  // on /tmp/bare_metal_gdb.lock.
  // TODO(crbug.com/354290): Remove this hack. Use __nacl_irt_open and
  // __nacl_irt_close instead of the direct syscalls when we add more
  // restrictions to the syscall sandbox.
  if (!__bare_metal_irt_notify_gdb_of_libraries) {
    while (true) {
      int fd = syscall(__NR_open, "/tmp/bare_metal_gdb.lock", O_RDONLY);
      if (fd < 0)
        break;
      syscall(__NR_close, fd);
    }
  }
#endif  // BARE_METAL_BIONIC
  // ARC MOD END

#if TIMING
    struct timeval t0, t1;
    gettimeofday(&t0, 0);
#endif
    // ARC MOD BEGIN
    // Load the main binary. See the comment for load_main_binary()
    // for detail.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
    load_main_binary(args);
#endif
    // ARC MOD END

    // Initialize environment functions, and get to the ELF aux vectors table.
    linker_env_init(args);

    // If this is a setuid/setgid program, close the security hole described in
    // ftp://ftp.freebsd.org/pub/FreeBSD/CERT/advisories/FreeBSD-SA-02:23.stdio.asc
    if (get_AT_SECURE()) {
        nullify_closed_stdio();
    }

    // ARC MOD BEGIN
    // NaCl does not have signal handlers so there is no reason we
    // need to call debugger_init, which depends on signals.
#if !defined(__native_client__) && !defined(BARE_METAL_BIONIC)
    // ARC MOD END
    debuggerd_init();
    // ARC MOD BEGIN
#endif
    // ARC MOD END

    // Get a few environment variables.
    const char* LD_DEBUG = linker_env_get("LD_DEBUG");
    if (LD_DEBUG != NULL) {
      gLdDebugVerbosity = atoi(LD_DEBUG);
    }

    // Normally, these are cleaned by linker_env_init, but the test
    // doesn't cost us anything.
    const char* ldpath_env = NULL;
    const char* ldpreload_env = NULL;
    if (!get_AT_SECURE()) {
      ldpath_env = linker_env_get("LD_LIBRARY_PATH");
      ldpreload_env = linker_env_get("LD_PRELOAD");
      // ARC MOD BEGIN
      // Currently, we have some canned shared objects in
      // /vendor/lib. In NDK direct execution mode, we need to be able
      // to open them when they are required by NDK shared objects.
      // TODO(crbug.com/364344): Remove /vendor/lib and this MOD.
#if defined(USE_NDK_DIRECT_EXECUTION)
      if (!ldpath_env)
        ldpath_env = kVendorLibDir;
#endif
      // ARC MOD END
    }

    INFO("[ android linker & debugger ]");

    // ARC MOD BEGIN
    // As sel_ldr does not load the main program, we loaded the main
    // binary by ourselves in load_main_binary. We should just reuse
    // it not to create an unnecessary element in the link list.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
    soinfo* si = solist->next;
#else
    // ARC MOD END
    soinfo* si = soinfo_alloc(args.argv[0]);
    // ARC MOD BEGIN
#endif
    // ARC MOD END
    if (si == NULL) {
        exit(EXIT_FAILURE);
    }

    /* bootstrap the link map, the main exe always needs to be first */
    si->flags |= FLAG_EXE;
    link_map_t* map = &(si->link_map);

    map->l_addr = 0;
    map->l_name = args.argv[0];
    map->l_prev = NULL;
    map->l_next = NULL;

    _r_debug.r_map = map;
    r_debug_tail = map;

    // ARC MOD BEGIN
    // We disable debug info related stuff. On NaCl, gdb will interact
    // with the loader in the host so we need to do nothing for it.
#if !defined(__native_client__) && !defined(BARE_METAL_BIONIC)
    // ARC MOD END
    /* gdb expects the linker to be in the debug shared object list.
     * Without this, gdb has trouble locating the linker's ".text"
     * and ".plt" sections. Gdb could also potentially use this to
     * relocate the offset of our exported 'rtld_db_dlactivity' symbol.
     * Don't use soinfo_alloc(), because the linker shouldn't
     * be on the soinfo list.
     */
    {
        static soinfo linker_soinfo;
        strlcpy(linker_soinfo.name, "/system/bin/linker", sizeof(linker_soinfo.name));
        linker_soinfo.flags = 0;
        linker_soinfo.base = linker_base;

        /*
         * Set the dynamic field in the link map otherwise gdb will complain with
         * the following:
         *   warning: .dynamic section for "/system/bin/linker" is not at the
         *   expected address (wrong library or version mismatch?)
         */
        Elf32_Ehdr *elf_hdr = (Elf32_Ehdr *) linker_base;
        Elf32_Phdr *phdr = (Elf32_Phdr*)((unsigned char*) linker_base + elf_hdr->e_phoff);
        phdr_table_get_dynamic_section(phdr, elf_hdr->e_phnum, linker_base,
                                       &linker_soinfo.dynamic, NULL, NULL);
        insert_soinfo_into_debug_map(&linker_soinfo);
    }

    // ARC MOD BEGIN
    // Note that we are in #if !defined(__native_client__) so this
    // code will not be used.
    //
    // We already initialized them in load_library.
    // ARC MOD END
    // Extract information passed from the kernel.
    si->phdr = reinterpret_cast<Elf32_Phdr*>(args.getauxval(AT_PHDR));
    si->phnum = args.getauxval(AT_PHNUM);
    si->entry = args.getauxval(AT_ENTRY);

    // ARC MOD BEGIN
    // Note that we are in #if !defined(__native_client__) so this
    // code will not be used.
    //
    // On NaCl, we load the main executable in load_main_binary
    // using load_library and |si| is already initialized in
    // load_library. So, we do not need to update these fields.
    // Also, arm-nacl-gcc maps PT_PHDR at the beginning of the data
    // segment, so this check is wrong.
    // ARC MOD END
    /* Compute the value of si->base. We can't rely on the fact that
     * the first entry is the PHDR because this will not be true
     * for certain executables (e.g. some in the NDK unit test suite)
     */
    si->base = 0;
    si->size = phdr_table_get_load_size(si->phdr, si->phnum);
    si->load_bias = 0;
    for (size_t i = 0; i < si->phnum; ++i) {
      if (si->phdr[i].p_type == PT_PHDR) {
        si->load_bias = reinterpret_cast<Elf32_Addr>(si->phdr) - si->phdr[i].p_vaddr;
        si->base = reinterpret_cast<Elf32_Addr>(si->phdr) - si->phdr[i].p_offset;
        break;
      }
    }
    si->dynamic = NULL;
    // ARC MOD BEGIN
#endif  // !__native_client__
    // ARC MOD END
    si->ref_count = 1;

    // Use LD_LIBRARY_PATH and LD_PRELOAD (but only if we aren't setuid/setgid).
    parse_LD_LIBRARY_PATH(ldpath_env);
    parse_LD_PRELOAD(ldpreload_env);

    somain = si;

    if (!soinfo_link_image(si)) {
        __libc_format_fd(2, "CANNOT LINK EXECUTABLE: %s\n", linker_get_error_buffer());
        exit(EXIT_FAILURE);
    }

    // ARC MOD BEGIN
    // Neither NaCl nor Bare Metal has VDSO.
#if !defined(__native_client__) && !defined(BARE_METAL_BIONIC)
    add_vdso(args);
#endif
    // ARC MOD END

    si->CallPreInitConstructors();

    for (size_t i = 0; gLdPreloads[i] != NULL; ++i) {
        gLdPreloads[i]->CallConstructors();
    }

    /* After the link_image, the si->load_bias is initialized.
     * For so lib, the map->l_addr will be updated in notify_gdb_of_load.
     * We need to update this value for so exe here. So Unwind_Backtrace
     * for some arch like x86 could work correctly within so exe.
     */
    // ARC MOD BEGIN UPSTREAM bionic-use-si-base
#if defined(__native_client__)
    // TODO(crbug.com/323864): Remove the path for __native_client__.
    map->l_addr = si->load_bias;
#else
    map->l_addr = si->base;
#endif
    // ARC MOD END UPSTREAM
    si->CallConstructors();

#if TIMING
    gettimeofday(&t1,NULL);
    PRINT("LINKER TIME: %s: %d microseconds", args.argv[0], (int) (
               (((long long)t1.tv_sec * 1000000LL) + (long long)t1.tv_usec) -
               (((long long)t0.tv_sec * 1000000LL) + (long long)t0.tv_usec)
               ));
#endif
#if STATS
    PRINT("RELO STATS: %s: %d abs, %d rel, %d copy, %d symbol", args.argv[0],
           linker_stats.count[kRelocAbsolute],
           linker_stats.count[kRelocRelative],
           linker_stats.count[kRelocCopy],
           linker_stats.count[kRelocSymbol]);
#endif
#if COUNT_PAGES
    {
        unsigned n;
        unsigned i;
        unsigned count = 0;
        for (n = 0; n < 4096; n++) {
            if (bitmask[n]) {
                unsigned x = bitmask[n];
                for (i = 0; i < 8; i++) {
                    if (x & 1) {
                        count++;
                    }
                    x >>= 1;
                }
            }
        }
        PRINT("PAGES MODIFIED: %s: %d (%dKB)", args.argv[0], count, count * 4);
    }
#endif

#if TIMING || STATS || COUNT_PAGES
    fflush(stdout);
#endif

    // ARC MOD BEGIN
    // Add a cast for x86-64.
    TRACE("[ Ready to execute '%s' @ 0x%08x ]", si->name, (uint32_t)si->entry);
    // ARC MOD END
    return si->entry;
}

// ARC MOD BEGIN
// This is only used for the relocation of the loader and NaCl do not
// relocate the loader for now.
#if !defined(__native_client__)
// ARC MOD END
/* Compute the load-bias of an existing executable. This shall only
 * be used to compute the load bias of an executable or shared library
 * that was loaded by the kernel itself.
 *
 * Input:
 *    elf    -> address of ELF header, assumed to be at the start of the file.
 * Return:
 *    load bias, i.e. add the value of any p_vaddr in the file to get
 *    the corresponding address in memory.
 */
static Elf32_Addr get_elf_exec_load_bias(const Elf32_Ehdr* elf) {
  Elf32_Addr        offset     = elf->e_phoff;
  const Elf32_Phdr* phdr_table = (const Elf32_Phdr*)((char*)elf + offset);
  const Elf32_Phdr* phdr_end   = phdr_table + elf->e_phnum;

  for (const Elf32_Phdr* phdr = phdr_table; phdr < phdr_end; phdr++) {
    if (phdr->p_type == PT_LOAD) {
      return reinterpret_cast<Elf32_Addr>(elf) + phdr->p_offset - phdr->p_vaddr;
    }
  }
  return 0;
}
// ARC MOD BEGIN
// This is only used for the relocation of the loader and NaCl do not
// relocate the loader for now.
#endif  // !__native_client__
// ARC MOD END

/*
 * This is the entry point for the linker, called from begin.S. This
 * method is responsible for fixing the linker's own relocations, and
 * then calling __linker_init_post_relocation().
 *
 * Because this method is called before the linker has fixed it's own
 * relocations, any attempt to reference an extern variable, extern
 * function, or other GOT reference will generate a segfault.
 */
extern "C" Elf32_Addr __linker_init(void* raw_args) {
  // ARC MOD BEGIN
  // Do not show messages from PRINT when --disable-debug-code is specified.
#if LINKER_DEBUG == 0
  gLdDebugVerbosity = -1;
#endif
  // ARC MOD END
  KernelArgumentBlock args(raw_args);

  Elf32_Addr linker_addr = args.getauxval(AT_BASE);

  // ARC MOD BEGIN
  // Print total time elapsed in the loader. Note that defining TIMING would
  // not help much because the TIMING code does not count the load_library
  // call for the main.nexe below.
  ScopedElapsedTimePrinter<__LINE__> printer(
      "Loaded", (const char*)((void**)raw_args)[1]  /* == argv[0] */);

  // On real Android, the Bionic loader is a shared object and it
  // has a few relocation entries whose type is R_*_RELATIVE maybe
  // for address randomization. For NaCl, we use statically linked
  // binary as the loader so we do not need to relocate the loader.
#if !defined(__native_client__)
  // ARC MOD END
  Elf32_Ehdr* elf_hdr = (Elf32_Ehdr*) linker_addr;
  Elf32_Phdr* phdr = (Elf32_Phdr*)((unsigned char*) linker_addr + elf_hdr->e_phoff);

  soinfo linker_so;
  memset(&linker_so, 0, sizeof(soinfo));

  linker_so.base = linker_addr;
  linker_so.size = phdr_table_get_load_size(phdr, elf_hdr->e_phnum);
  linker_so.load_bias = get_elf_exec_load_bias(elf_hdr);
  linker_so.dynamic = NULL;
  linker_so.phdr = phdr;
  linker_so.phnum = elf_hdr->e_phnum;
  linker_so.flags |= FLAG_LINKER;

  if (!soinfo_link_image(&linker_so)) {
    // It would be nice to print an error message, but if the linker
    // can't link itself, there's no guarantee that we'll be able to
    // call write() (because it involves a GOT reference).
    //
    // This situation should never occur unless the linker itself
    // is corrupt.
    exit(EXIT_FAILURE);
  }
  // ARC MOD BEGIN
#endif  // !__native_client__
  // ARC MOD END

  // We have successfully fixed our own relocations. It's safe to run
  // the main part of the linker now.
  args.abort_message_ptr = &gAbortMessage;
  Elf32_Addr start_address = __linker_init_post_relocation(args, linker_addr);

  set_soinfo_pool_protection(PROT_READ);

  // Return the address that the calling assembly stub should jump to.
  return start_address;
}
// ARC MOD BEGIN
// Linux kernel maps segments of the main binary before it runs the
// loader and sends the information about it using auxvals (e.g.,
// AT_PHDR). Neither NaCl nor Bare Metal service runtime does this so
// we need to load the main binary by ourselves.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)

static void load_main_binary(KernelArgumentBlock& args) {
    if (args.argc < 1) {
        DL_ERR("no file\n");
        exit(-1);
    }

    struct soinfo* si = load_library(args.argv[0]);
    if (!si) {
        DL_ERR("Failed to load %s\n", args.argv[0]);
        exit(-1);
    }

    // Note that we use Elf32_auxv even on NaCl x86-64.
    Elf32_auxv_t* auxv = args.auxv;
    // auxv[0] and auxv[1] were filled by _start for AT_SYSINFO and
    // AT_BASE, and we must not update them. See
    // bionic/linker/arch/nacl/begin.c for detail.
    if (auxv[0].a_type != AT_SYSINFO || !auxv[0].a_un.a_val) {
        DL_ERR("auxv[0] is not filled.\n");
        exit(-1);
    }
    if (auxv[1].a_type != AT_BASE) {
        DL_ERR("auxv[1].a_type is not filled.\n");
        exit(-1);
    }
    if (auxv[2].a_type != AT_NULL || auxv[2].a_un.a_val) {
        DL_ERR("auxv[2] has already been filled.\n");
        exit(-1);
    }
    int i = 2;
    auxv[i].a_type = AT_PHDR;
    auxv[i++].a_un.a_val = (uint32_t)si->phdr;
    auxv[i].a_type = AT_PHNUM;
    auxv[i++].a_un.a_val = si->phnum;
    auxv[i].a_type = AT_ENTRY;
    auxv[i++].a_un.a_val = (uint32_t)si->entry;
    auxv[i].a_type = AT_NULL;
    auxv[i++].a_un.a_val = 0;
}

#endif
// ARC MOD END
