// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// The bootstrap ELF loader of Bare Metal ARC.
//

#ifndef BARE_METAL_COMMON_LOADER_H_
#define BARE_METAL_COMMON_LOADER_H_

#include <string>

#include "base/basictypes.h"

namespace bare_metal {

class Loader {
 public:
  static Loader* Create(const std::string& binary_filename);
  virtual ~Loader();

  // Loads a program into the memory.
  virtual void Load(int fd) = 0;

  // Runs a program loaded by Load(). |argc| and |argv| will be
  // directly passed to the loaded program, so they should not contain
  // the Bare Metal loader itself.
  virtual void Run(int argc, char* argv[]) = 0;

 protected:
  Loader();

 private:
  DISALLOW_COPY_AND_ASSIGN(Loader);
};

}  // namespace bare_metal

#endif  // BARE_METAL_COMMON_LOADER_H_
