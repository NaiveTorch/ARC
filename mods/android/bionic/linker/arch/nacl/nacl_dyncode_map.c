// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/nacl_dyncode_map.c"
// ARC MOD BEGIN
// Copyright and #include lines.
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

// TODO(crbug.com/362816): Once Chrome OS stable is updated to >=r269210,
// replace the fallback mmap path below with 'return -1'.

#include <errno.h>
#include <sys/mman.h>

#include <irt_syscalls.h>

// Add declarations of __mmap, __munmap, and __nacl_dyncode_create.
void *__mmap(void *addr, size_t length, int prot, int flags,
             int fd, off_t offset);
int __munmap(void *addr, size_t length);
int __nacl_dyncode_create(void *dest, const void *src, size_t size);

void print_format(const char* fmt, ...);
// ARC MOD END

/* Dynamically load code from a file.  One day NaCl might provide a
   syscall that provides this functionality without needing to make a
   copy of the code.  offset and size do not need to be page-aligned. */
int nacl_dyncode_map (int fd, void *dest, size_t offset, size_t size)
{
  size_t alignment_padding = offset & (getpagesize() - 1);
  uint8_t *mapping;
  if (alignment_padding == 0 && (size & (getpagesize() - 1)) == 0) {
    /* First try mmap using PROT_EXEC directly. */
    mapping = __mmap(dest, size, PROT_READ | PROT_EXEC,
                     MAP_PRIVATE | MAP_FIXED, fd, offset);
    if (mapping == dest) {
      return 0;
    } else if (mapping != MAP_FAILED) {
      /* Mapped to an unexpected location.  Unmap and fall back. */
      __munmap(mapping, size);
      // ARC MOD BEGIN
    } else {
      print_format("nacl_dyncode_map: mmap(%x) failed with %d. "
                   "Falling back to the slow path (crbug.com/360277)\n",
                   (long)dest, errno);
      // ARC MOD END
    }
  }
  mapping = __mmap (NULL, size + alignment_padding,
                    PROT_READ, MAP_PRIVATE, fd,
                    offset - alignment_padding);
  if (mapping == MAP_FAILED)
    return -1;
  // ARC MOD BEGIN
  // |dest| is aligned for us, and debugging code.
  int result = __nacl_dyncode_create((char *)dest + alignment_padding,
                                     mapping + alignment_padding, size);

  // We do not support valgrind for now.
  // TODO(crbug.com/243244): Figure out if we can/should support this.
#if 0
  /* Tell Valgrind about this mapping. */
  __nacl_dyncode_map_for_valgrind(dest, size, offset, mapping);
#endif

  // ARC MOD END
  int munmap_result = __munmap (mapping, size);
  if (result != 0 || munmap_result != 0)
    return -1;
  return 0;
}
