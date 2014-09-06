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

#ifndef _LINKER_H_
#define _LINKER_H_

#include <unistd.h>
#include <sys/types.h>
#include <elf.h>
#include <sys/exec_elf.h>

#include <link.h>

#include "private/libc_logging.h"
// ARC MOD BEGIN
// For __nacl_irt_query_fn_t.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#endif

// We usually define macros like ElfW(type) so ElfW(Ehdr) can be
// either Elf32_Ehdr or Elf64_Ehdr. However, we map all Elf32_* types
// to Elf64_* types to minimize the number of ARC MOD.
#if defined(ANDROID_X86_64_LINKER)
#define Elf32_Addr Elf64_Addr
#define Elf32_Ehdr Elf64_Ehdr
#define Elf32_Half Elf64_Half
#define Elf32_Phdr Elf64_Phdr
#define Elf32_Sym Elf64_Sym
#define Elf32_Dyn Elf64_Dyn
#endif

// linker.cpp does not have as many following macros as the above
// structure types. We can make the ideal change for them.
#if defined(ANDROID_X86_64_LINKER)
#define ELFW(x) ELF64_ ## x
#else
#define ELFW(x) ELF32_ ## x
#endif

// ARC MOD END
#define DL_ERR(fmt, x...) \
    do { \
      __libc_format_buffer(linker_get_error_buffer(), linker_get_error_buffer_size(), fmt, ##x); \
      /* If LD_DEBUG is set high enough, log every dlerror(3) message. */ \
      /* ARC MOD BEGIN */                                             \
      /* Use PRINT instead of DEBUG and remove unnecessary \n. */       \
      PRINT("%s", linker_get_error_buffer());                           \
      /* ARC MOD END */                                               \
    } while (false)

#define DL_WARN(fmt, x...) \
    do { \
      __libc_format_log(ANDROID_LOG_WARN, "linker", fmt, ##x); \
      __libc_format_fd(2, "WARNING: linker: "); \
      __libc_format_fd(2, fmt, ##x); \
      __libc_format_fd(2, "\n"); \
    } while (false)


// Returns the address of the page containing address 'x'.
#define PAGE_START(x)  ((x) & PAGE_MASK)

// Returns the offset of address 'x' in its page.
#define PAGE_OFFSET(x) ((x) & ~PAGE_MASK)

// Returns the address of the next page after address 'x', unless 'x' is
// itself at the start of a page.
#define PAGE_END(x)    PAGE_START((x) + (PAGE_SIZE-1))

// Magic shared structures that GDB knows about.

struct link_map_t {
  // ARC MOD BEGIN
  // GDB expects this to be a 64 bit integer on x86-64 NaCl.
  // See third_party/nacl-glibc/elf/link.h.
#if defined(ANDROID_X86_64_LINKER) && defined(__native_client__)
  Elf64_Addr l_addr;
#else
  // ARC MOD END
  uintptr_t l_addr;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  char*  l_name;
  uintptr_t l_ld;
  link_map_t* l_next;
  link_map_t* l_prev;
};

// Values for r_debug->state
enum {
  RT_CONSISTENT,
  RT_ADD,
  RT_DELETE
};

struct r_debug {
  int32_t r_version;
  link_map_t* r_map;
  // ARC MOD BEGIN
  // GDB expects r_brk and r_ldbase to be 64 bit values on x86-64 NaCl.
  // See third_party/nacl-glibc/elf/link.h.
#if defined(ANDROID_X86_64_LINKER) && defined(__native_client__)
  Elf64_Addr r_brk;
  int32_t r_state;
  Elf64_Addr r_ldbase;
#else
  // ARC MOD END
  void (*r_brk)(void);
  int32_t r_state;
  uintptr_t r_ldbase;
    // ARC MOD BEGIN
#endif
    // ARC MOD END
};

#define FLAG_LINKED     0x00000001
#define FLAG_EXE        0x00000004 // The main executable
#define FLAG_LINKER     0x00000010 // The linker itself

#define SOINFO_NAME_LEN 128

typedef void (*linker_function_t)();

struct soinfo {
 public:
  char name[SOINFO_NAME_LEN];
  const Elf32_Phdr* phdr;
  size_t phnum;
  Elf32_Addr entry;
  Elf32_Addr base;
  // ARC MOD BEGIN
  // There are no code change, but the meaning of this field has
  // changed. In the original Bionic, this field contains the total
  // size loaded segments and it assumes there are no gaps between
  // each segment. For NaCl, we use this field as the size of the
  // text segment. NaCl binary has a big gap between the text
  // segment and the data segments so if we use the original value,
  // find_containing_library will not return the correct library.
  // ARC MOD END
  unsigned size;

  uint32_t unused1;  // DO NOT USE, maintained for compatibility.

  Elf32_Dyn* dynamic;

  uint32_t unused2; // DO NOT USE, maintained for compatibility
  uint32_t unused3; // DO NOT USE, maintained for compatibility

  soinfo* next;
  unsigned flags;

  const char* strtab;
  Elf32_Sym* symtab;

  size_t nbucket;
  size_t nchain;
  unsigned* bucket;
  unsigned* chain;

  unsigned* plt_got;

  // ARC MOD BEGIN
  // System V Application Binary Interface AMD64 Architecture
  // Processor Supplement says "The AMD64 ABI architectures uses
  // only Elf64_Rela relocation entries with explicit addends."
  // http://www.x86-64.org/documentation/abi.pdf
#if defined(ANDROID_X86_64_LINKER)
  Elf64_Rela *plt_rel;
#else
  // ARC MOD END
  Elf32_Rel* plt_rel;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  size_t plt_rel_count;

  // ARC MOD BEGIN
  // AMD64 ABI says we should always use Elf64_Rela for x86-64.
#if defined(ANDROID_X86_64_LINKER)
  Elf64_Rela *rel;
#else
  // ARC MOD END
  Elf32_Rel* rel;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  size_t rel_count;

  linker_function_t* preinit_array;
  size_t preinit_array_count;

  linker_function_t* init_array;
  size_t init_array_count;
  linker_function_t* fini_array;
  size_t fini_array_count;

  // ARC MOD BEGIN
  // We pass __nacl_irt_query from the loader to libc.so linked
  // against the main executable. In nacl-glibc, the loader passes
  // __nacl_irt_query using AT_SYSINFO when the loader calls _start
  // in the main executable. However, we cannot do this for Bionic
  // because the loader of Bionic calls initializer functions in
  // .ctors section before it calls _start.
#if defined(__native_client__) || defined(BARE_METAL_BIONIC)
  void (*init_func)(__nacl_irt_query_fn_t irt_query);
#else
  // ARC MOD END
  linker_function_t init_func;
  // ARC MOD BEGIN
#endif
  // ARC MOD END
  linker_function_t fini_func;

#if defined(ANDROID_ARM_LINKER)
  // ARM EABI section used for stack unwinding.
  unsigned* ARM_exidx;
  size_t ARM_exidx_count;
#elif defined(ANDROID_MIPS_LINKER)
  unsigned mips_symtabno;
  unsigned mips_local_gotno;
  unsigned mips_gotsym;
#endif

  size_t ref_count;
  link_map_t link_map;

  bool constructors_called;

  // When you read a virtual address from the ELF file, add this
  // value to get the corresponding address in the process' address space.
  Elf32_Addr load_bias;

  bool has_text_relocations;
  bool has_DT_SYMBOLIC;
  // ARC MOD BEGIN
  // Add is_ndk for NDK direct execution. This will be used to decide
  // the semantics of symbol resolution for this binary.
#if defined(USE_NDK_DIRECT_EXECUTION)
  bool is_ndk;
#endif
  // ARC MOD END

  void CallConstructors();
  void CallDestructors();
  void CallPreInitConstructors();

 private:
  void CallArray(const char* array_name, linker_function_t* functions, size_t count, bool reverse);
  void CallFunction(const char* function_name, linker_function_t function);
};

extern soinfo libdl_info;
// ARC MOD BEGIN
// Add x86-64 relocations types. Copied from
// http://svnweb.freebsd.org/base/head/sys/sys/elf_common.h?revision=249558
#if defined(ANDROID_X86_64_LINKER)
#define R_X86_64_NONE           0       /* No relocation. */
#define R_X86_64_64             1       /* Add 64 bit symbol value. */
#define R_X86_64_PC32           2       /* PC-relative 32 bit signed sym value. */
#define R_X86_64_GOT32          3       /* PC-relative 32 bit GOT offset. */
#define R_X86_64_PLT32          4       /* PC-relative 32 bit PLT offset. */
#define R_X86_64_COPY           5       /* Copy data from shared object. */
#define R_X86_64_GLOB_DAT       6       /* Set GOT entry to data address. */
#define R_X86_64_JMP_SLOT       7       /* Set GOT entry to code address. */
#define R_X86_64_RELATIVE       8       /* Add load address of shared object. */
#define R_X86_64_GOTPCREL       9       /* Add 32 bit signed pcrel offset to GOT. */
#define R_X86_64_32             10      /* Add 32 bit zero extended symbol value */
#define R_X86_64_32S            11      /* Add 32 bit sign extended symbol value */
#define R_X86_64_16             12      /* Add 16 bit zero extended symbol value */
#define R_X86_64_PC16           13      /* Add 16 bit signed extended pc relative symbol value */
#define R_X86_64_8              14      /* Add 8 bit zero extended symbol value */
#define R_X86_64_PC8            15      /* Add 8 bit signed extended pc relative symbol value */
#define R_X86_64_DTPMOD64       16      /* ID of module containing symbol */
#define R_X86_64_DTPOFF64       17      /* Offset in TLS block */
#define R_X86_64_TPOFF64        18      /* Offset in static TLS block */
#define R_X86_64_TLSGD          19      /* PC relative offset to GD GOT entry */
#define R_X86_64_TLSLD          20      /* PC relative offset to LD GOT entry */
#define R_X86_64_DTPOFF32       21      /* Offset in TLS block */
#define R_X86_64_GOTTPOFF       22      /* PC relative offset to IE GOT entry */
#define R_X86_64_TPOFF32        23      /* Offset in static TLS block */
#define R_X86_64_IRELATIVE      37
#endif
// ARC MOD END

// These aren't defined in <sys/exec_elf.h>.
#ifndef DT_PREINIT_ARRAY
#define DT_PREINIT_ARRAY   32
#endif
#ifndef DT_PREINIT_ARRAYSZ
#define DT_PREINIT_ARRAYSZ 33
#endif

void do_android_update_LD_LIBRARY_PATH(const char* ld_library_path);
soinfo* do_dlopen(const char* name, int flags);
int do_dlclose(soinfo* si);

Elf32_Sym* dlsym_linear_lookup(const char* name, soinfo** found, soinfo* start);
soinfo* find_containing_library(const void* addr);

Elf32_Sym* dladdr_find_symbol(soinfo* si, const void* addr);
Elf32_Sym* dlsym_handle_lookup(soinfo* si, const char* name);

void debuggerd_init();
extern "C" abort_msg_t* gAbortMessage;
extern "C" void notify_gdb_of_libraries();

char* linker_get_error_buffer();
size_t linker_get_error_buffer_size();

#endif
