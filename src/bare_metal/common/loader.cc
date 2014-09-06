// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Bare Metal loader has three responsibilities:
//
// 1. Load an ELF binary (the Bionic loader) into memory.
// 2. Provide IRT interfaces to the Bionic loader.
// 3. Call the entry point of the Bionic loader.
//
// Note that this loader does not need to support relocations or
// shared objects.
//
// TODO(crbug.com/266627): As for IRT interfaces, we might want to
// reuse the direct-call IRT which NaCl team has started implementing.
// http://src.chromium.org/viewvc/native_client?revision=12218&view=revision
//
// To implement Bare Metal loader, we use a part of the Bionic loader
// which mmaps segments in an ELF binary (bionic/linker/linker_phdr.c).
// We do not reuse entire Bionic loader for the following reasons:
//
// 1. We will need to prepare IRT in the Bare Metal loader and it
//    should invoke the entry point of an ELF binary with NaCl ABI
//    to pass __nacl_irt_query.
// 2. We do not support relocations or shared objects.
//

#include "bare_metal/common/loader.h"

#include <link.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "bare_metal/common/bare_metal_irt.h"
#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_core.h"
#include "bare_metal/common/irt_interfaces.h"
#include "bare_metal/common/log.h"
#include "base/compiler_specific.h"
#include "bionic/linker/linker_phdr.h"

extern char** environ;

// TODO(crbug.com/266627): Change this to 0, or replace log.h with
// common/alog.h.
int g_verbosity = 1;

namespace bare_metal {

const int kMaxBinaryHeadersSize = 4096;

class LoaderImpl : public Loader {
 public:
  explicit LoaderImpl(const std::string& binary_filename);
  virtual ~LoaderImpl();

  virtual void Load(int fd) OVERRIDE;
  virtual void Run(int argc, char* argv[]) OVERRIDE;

 private:
  // The filename of the binary.
  const std::string binary_filename_;
  // The entry address of the program loaded.
  Elf32_Addr entry_;

  DISALLOW_COPY_AND_ASSIGN(LoaderImpl);
};

Loader* Loader::Create(const std::string& binary_filename) {
  return new LoaderImpl(binary_filename);
}

Loader::Loader() {
}

Loader::~Loader() {
}

LoaderImpl::LoaderImpl(const std::string& binary_filename)
    : binary_filename_(binary_filename),
      entry_(0) {
}

LoaderImpl::~LoaderImpl() {
}

void LoaderImpl::Load(int fd) {
  CHECK(fd >=0, "Invalid fd: %d", fd);

  // Bare Metal loader only loads the Bionic loader.
  const char* kRunnableLd = "runnable-ld.so";
  ElfReader elf(kRunnableLd, fd);
  elf.Load();
  entry_ = elf.header().e_entry + elf.load_bias();

  // Let GDB know the Bionic loader.
  link_map lm;
  lm.l_name = const_cast<char*>(binary_filename_.c_str());
  lm.l_addr = elf.load_bias();
  bare_metal_irt_notify_gdb_of_load(&lm);
}

void LoaderImpl::Run(int argc, char* argv[]) {
  CHECK(entry_, "%s: Load() must be called before Run()",
        binary_filename_.c_str());
  CHECK(argc > 0, "%s: argc is too small: %d", binary_filename_.c_str(), argc);
  CHECK(argv, "%s: argv must not be NULL", binary_filename_.c_str());
  CHECK(*argv, "%s: *argv must not be NULL", binary_filename_.c_str());

  int envc;
  for (envc = 0; environ && environ[envc]; envc++) {}
  // 3 for fini, envc, and argc. Then, argv and envp, with their NULL
  // terminators. We will have 4 elements in auxv. See
  // mods/android/bionic/linker/arch/nacl/begin.c as well.
  uintptr_t* info = static_cast<uintptr_t*>(
      alloca(sizeof(uintptr_t) * (3 + argc + 1 + envc + 1 + 4)));
  int j = 0;
  info[j++] = 0;  // The Bionic loader does not use fini.
  info[j++] = envc;
  info[j++] = argc;
  for (int i = 0; i < argc; i++)
    info[j++] = reinterpret_cast<uintptr_t>(argv[i]);
  info[j++] = 0;
  for (int i = 0; i < envc; i++)
    info[j++] = reinterpret_cast<uintptr_t>(environ[i]);
  info[j++] = 0;
  // We pass the address of __nacl_irt_query so that the Bionic loader
  // can get other IRT functions.
  info[j++] = AT_SYSINFO;
  info[j++] = reinterpret_cast<uintptr_t>(&nacl_irt_query_core);
  info[j++] = AT_NULL;
  info[j++] = 0;

  VLOG(1, "Booting from entry address 0x%x", entry_);

  reinterpret_cast<void (*)(uintptr_t* info)>(entry_)(info);
}

}  // namespace bare_metal
