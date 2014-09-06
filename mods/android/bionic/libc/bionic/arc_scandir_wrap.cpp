// ARC MOD TRACK "third_party/android/bionic/libc/bionic/scandir.cpp"
/*
 * Copyright (C) 2013 The Android Open Source Project
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

#include <dirent.h>

#include <errno.h>
#include <stdlib.h>

// ARC MOD BEGIN
// Include arc_strace.h.
#include "common/arc_strace.h"

// The following is an inline include of
// "third_party/android/bionic/libc/private/ScopedReaddir.h".
// This file is used in src/wrap and we inline include ScopedReaddir
// to prevent the need to include headers deep inside Android source.
#ifndef SCOPED_READDIR_H
#define SCOPED_READDIR_H

class ScopedReaddir {
 public:
  ScopedReaddir(const char* path) {
    dir_ = opendir(path);
  }

  ~ScopedReaddir() {
    if (dir_ != NULL) {
      closedir(dir_);
    }
  }

  bool IsBad() {
    return dir_ == NULL;
  }

  dirent* ReadEntry() {
    return readdir(dir_);
  }

 private:
  DIR* dir_;

  // Disallow copy and assignment.
  ScopedReaddir(const ScopedReaddir&);
  void operator=(const ScopedReaddir&);
};

#endif // SCOPED_READDIR_H

// See the comment in pepper_fs_dir_wrap.cc for the reason why we have
// the copy of scandir implementation.

// Make all these functions wrap functions.
#define scandir __wrap_scandir
// ARC MOD END

// A smart pointer to the scandir dirent**.
class ScandirResult {
 public:
  ScandirResult() : names_(NULL), size_(0), capacity_(0) {
  }

  ~ScandirResult() {
    while (size_ > 0) {
      free(names_[--size_]);
    }
    free(names_);
  }

  size_t size() {
    return size_;
  }

  dirent** release() {
    dirent** result = names_;
    names_ = NULL;
    size_ = capacity_ = 0;
    return result;
  }

  bool Add(dirent* entry) {
    if (size_ >= capacity_) {
      size_t new_capacity = capacity_ + 32;
      dirent** new_names = (dirent**) realloc(names_, new_capacity * sizeof(dirent*));
      if (new_names == NULL) {
        return false;
      }
      names_ = new_names;
      capacity_ = new_capacity;
    }

    dirent* copy = CopyDirent(entry);
    if (copy == NULL) {
      return false;
    }
    names_[size_++] = copy;
    return true;
  }

  void Sort(int (*comparator)(const dirent**, const dirent**)) {
    // If we have entries and a comparator, sort them.
    if (size_ > 0 && comparator != NULL) {
      qsort(names_, size_, sizeof(dirent*), (int (*)(const void*, const void*)) comparator);
    }
  }

 private:
  dirent** names_;
  size_t size_;
  size_t capacity_;

  static dirent* CopyDirent(dirent* original) {
    // Allocate the minimum number of bytes necessary, rounded up to a 4-byte boundary.
    size_t size = ((original->d_reclen + 3) & ~3);
    dirent* copy = (dirent*) malloc(size);
    memcpy(copy, original, original->d_reclen);
    return copy;
  }

  // Disallow copy and assignment.
  ScandirResult(const ScandirResult&);
  void operator=(const ScandirResult&);
};

// ARC MOD BEGIN
// Add extern "C".
extern "C"
// ARC MOD END
int scandir(const char* dirname, dirent*** name_list,
            int (*filter)(const dirent*),
            int (*comparator)(const dirent**, const dirent**)) {
  // ARC MOD BEGIN
  // Add ARC_STRACE calls.
  ARC_STRACE_ENTER_FD("scandir", "%s, %p, %p, %p",
                        SAFE_CSTR(dirname), name_list, filter, comparator);
  // ARC MOD END
  ScopedReaddir reader(dirname);
  if (reader.IsBad()) {
    // ARC MOD BEGIN
    ARC_STRACE_RETURN(-1);
    // ARC MOD END
  }

  ScandirResult names;
  dirent* entry;
  while ((entry = reader.ReadEntry()) != NULL) {
    // If we have a filter, skip names that don't match.
    if (filter != NULL && !(*filter)(entry)) {
      continue;
    }
    names.Add(entry);
  }

  names.Sort(comparator);

  size_t size = names.size();
  *name_list = names.release();
  // ARC MOD BEGIN
  ARC_STRACE_RETURN(size);
  // ARC MOD END
}
