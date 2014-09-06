// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/nacl_dyncode_alloc.c"
// ARC MOD BEGIN
// Add a copyright.
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
// ARC MOD END

#include <assert.h>
#include <sys/mman.h>
#include <unistd.h>

// ARC MOD BEGIN
// Removed #include ldsodefs.h
// ARC MOD END
#include <nacl_dyncode.h>


static char *nacl_next_code;
static char *nacl_next_data;

// ARC MOD BEGIN
// Add declarations of __mmap and __munmap.
void *__mmap(void *addr, size_t length, int prot, int flags,
             int fd, off_t offset);
int __munmap(void *addr, size_t length);

// Use NACL_PAGE_SIZE instead of dl_pagesize.
static size_t round_up_to_pagesize(size_t val) {
  static const unsigned NACL_PAGE_SIZE = 0x10000;
  return (val + NACL_PAGE_SIZE - 1) & ~(NACL_PAGE_SIZE - 1);
}
// ARC MOD END

static void nacl_dyncode_alloc_init (void)
{
  extern char __etext[]; /* Defined by the linker script */

  if (nacl_next_code)
    {
      return;
    }

  /* Place data after whatever brk() heap has been allocated so far. This will
     mean the brk() heap cannot be extended any further.
     TODO(mseaborn): Ideally place ld.so and brk() heap at a high address so
     that library data can be mapped below and not get in the way of the brk()
     heap.  */
  nacl_next_code = __etext;
  // ARC MOD BEGIN
  // Use _end instead of __sbrk(0) as the initial value of
  // nacl_next_data. _end is placed at the end of the data segment of
  // runnable-ld.so by runnable-ld.lds which is the linker script for
  // the binary:
  // _end = .; PROVIDE (end = .); . = DATA_SEGMENT_END(.);
  // TODO(crbug.com/264596): Use the upstream nacl-glibc code.
  extern char _end[];
  nacl_next_data = _end;
  // ARC MOD END
}

/* Allocate space for code and data simultaneously.
   This is a simple allocator that doesn't know how to deallocate.  */
void *nacl_dyncode_alloc (size_t code_size, size_t data_size,
                          size_t data_offset)
{
  assert (data_offset == round_up_to_pagesize (data_offset));

  nacl_dyncode_alloc_init ();

  code_size = round_up_to_pagesize (code_size);
  data_size = round_up_to_pagesize (data_size);

  if (data_size != 0)
    {
      size_t last_offset = nacl_next_data - nacl_next_code;
      if (data_offset > last_offset)
        {
          /* Leaves unused space in the data area. */
          nacl_next_data += data_offset - last_offset;
        }
      else if (data_offset < last_offset)
        {
          /* Leaves unused space in the code area. */
          nacl_next_code += last_offset - data_offset;
        }
      assert (nacl_next_code + data_offset == nacl_next_data);

      /* Check whether the data space is available and reserve it.
         MAP_FIXED cannot be used because it overwrites existing mappings.
         Instead, fail if returned value is different from address hint.
         TODO(mseaborn): Retry on failure or avoid failure by
         reserving a big chunk of address space at startup. */
      void *mapped = __mmap (nacl_next_data, data_size, PROT_NONE,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
      if (mapped == MAP_FAILED)
        {
          return NULL;
        }
      if (mapped != nacl_next_data)
        {
          // ARC MOD BEGIN UPSTREAM nacl-fix-memory-corruption-dyncode-alloc
          // Changed |nacl_next_data| to |mapped|.
          __munmap (mapped, data_size);
          // ARC MOD END UPSTREAM
          return NULL;
        }
    }

  void *code_addr = nacl_next_code;
  nacl_next_data += data_size;
  nacl_next_code += code_size;
  return code_addr;
}

void *nacl_dyncode_alloc_fixed (void *dest, size_t code_size, size_t data_size,
                                size_t data_offset)
{
  /* TODO(eaeltsin): probably these alignment requirements are overly strict.
     If really so, support unaligned case.  */
  // ARC MOD BEGIN
  // Add casts to size_t.
  assert ((size_t)dest == round_up_to_pagesize ((size_t)dest));
  // ARC MOD END
  assert (data_offset == round_up_to_pagesize (data_offset));

  nacl_dyncode_alloc_init ();

  // ARC MOD BEGIN
  // Add a cast to char *.
  if (nacl_next_code > (char *)dest)
  // ARC MOD END
    {
      return NULL;
    }
  nacl_next_code = dest;

  code_size = round_up_to_pagesize (code_size);
  data_size = round_up_to_pagesize (data_size);

  if (data_size != 0)
    {
      size_t last_offset = nacl_next_data - nacl_next_code;
      if (data_offset > last_offset)
        {
          /* Leaves unused space in the data area. */
          nacl_next_data += data_offset - last_offset;
        }
      else if (data_offset < last_offset)
        {
          /* Cannot move code. */
          return NULL;
        }
      assert (nacl_next_code + data_offset == nacl_next_data);

      /* Check whether the data space is available and reserve it.
         MAP_FIXED cannot be used because it overwrites existing mappings.
         Instead, fail if returned value is different from address hint.  */
      void *mapped = __mmap (nacl_next_data, data_size, PROT_NONE,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
      if (mapped == MAP_FAILED)
        {
          return NULL;
        }
      if (mapped != nacl_next_data)
        {
          // ARC MOD BEGIN UPSTREAM nacl-fix-memory-corruption-dyncode-alloc
          // Changed |nacl_next_data| to |mapped|.
          __munmap (mapped, data_size);
          // ARC MOD END UPSTREAM
          return NULL;
        }
    }

  nacl_next_data += data_size;
  nacl_next_code += code_size;
  return dest;
}
