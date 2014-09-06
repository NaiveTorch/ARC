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
// TODO(crbug.com/348119): Reimplement this as described in 348119. We should
// completely remove the current code since this is just a temporary workaround
// copied from arc/src/ndk_translation/code_manager.cc.

#include <assert.h>
#include <stdlib.h>
#include <unistd.h>

#include "nacl/nacl_dyncode.h"

struct NaClMemMappingInfo {
  uint32_t start;
  uint32_t size;
  uint32_t prot;
  uint32_t max_prot;
  uint32_t vmmap_type;
};
int nacl_list_mappings(
    struct NaClMemMappingInfo* info, size_t count, size_t* result_count);

static uint8_t* align_ptr(uint8_t* ptr, uintptr_t mask) {
  return (uint8_t*)((uintptr_t)ptr & ~mask);
}

// Returns the highest used memory region in [search_start, search_end).
static uint8_t* find_highest_used_region(uint8_t* search_start,
                                         uint8_t* search_end,
                                         uintptr_t page_size) {
  assert((uintptr_t)search_start % page_size == 0);
  assert((uintptr_t)search_end % page_size == 0);

  static const size_t kDummyCodeSize = 32;
  uint8_t dummy_code[kDummyCodeSize];
#if defined(__i386__) || defined(__x86_64__)
  memset(dummy_code, 0x90, kDummyCodeSize);  // nop
#elif defined(__arm__)
  memset(dummy_code, 0x00, kDummyCodeSize);  // andeq r0, r0, r0 (i.e. no-op)
#else
#error unsupported architecture
#endif

  for (uint8_t* p = search_end - page_size; p >= search_start; p -= page_size) {
    if (nacl_dyncode_create(p, dummy_code, kDummyCodeSize) == 0) {
      // It is better to call nacl_dyncode_delete(p, page_size) here and return
      // |p + page_size| not to waste the page allocated above, but calling
      // nacl_dyncode_delete() does not succeed when multiple threads are
      // running (see native-client:2815).
      return p;
    }
  }
  return search_start;  // all pages in the range are in use.
}

// Returns page aligned region of |size|, suitable for further use with
// nacl_dyncode_create().
void* __allocate_nacl_dyncode(size_t size) {
  // NaCl's dynamic loader allocates memory from the lower address of
  // the text segment (0x00000000 - 0x10000000) for DT_NEEDED and
  // dlopen'ed binaries. We use higher region of the text segment to
  // avoid a conflict with the binaries the loader loads. As NaCl IRT
  // uses the highest pages, we return a text region right before NaCl IRT.
  // As of Feb 2014, NaCl IRT uses ~6MB of the text area and its address
  // is 0xfa00000-0xfef0000 (i686) and 0xfa00000-0xfd70000 (x86_64).
  const uintptr_t page_size = sysconf(_SC_PAGESIZE);
  const uintptr_t page_mask = page_size - 1;

  static const uint32_t kEstimatedIRTStartAddress = 0xfa00000;
  static const uint32_t kEstimatedIRTEndAddress = 0xfd70000;
  const uint32_t middle =
      (kEstimatedIRTStartAddress + kEstimatedIRTEndAddress) / 2;
  uint8_t* region_end =
      find_highest_used_region((uint8_t*)0x00000000,
                               align_ptr((uint8_t*)middle, page_mask),
                               page_size);
  assert(region_end != NULL);
  uint8_t* region_start = align_ptr(region_end - size, page_mask);

  // Maximum number of mappings, be generous here, as we
  // only execute this code once or few times.
  const uint32_t kMaxMappings = 0x10000;
  struct NaClMemMappingInfo* map = (struct NaClMemMappingInfo*)malloc(
      sizeof(struct NaClMemMappingInfo) * kMaxMappings);
  size_t ret_size = 0;
  int result = nacl_list_mappings(map, kMaxMappings, &ret_size);
  if (result != 0 || ret_size == 0) {
    free(map);
    return region_start;
  }

  // For production mode, nacl_list_mappings is not available, but if
  // nacl_list_mappings is available, we make sure our region does not
  // conflict with other regions used by DSOs including NaCl IRT.
  for (size_t i = 0; i < ret_size; ++i) {
    uint8_t* current_region = (uint8_t*)map[i].start;
    assert(region_start + size <= current_region ||
           current_region + map[i].size <= region_start);
  }

  free(map);
  return region_start;
}
