// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// This file lists private interfaces to file_wrap.c - meant
// only for testing.

#include <sys/types.h>
#include <string>

#ifndef WRAP_FILE_WRAP_PRIVATE_H_
#define WRAP_FILE_WRAP_PRIVATE_H_

namespace arc {

class VirtualFileSystemInterface;

std::string GetAndroidRoot();
#if !defined(__native_client__)
std::string GetLoadLibraryPath();
std::string FixDlopenPath(const std::string& filename);
#endif

// Gets a VirtualFileSystem instance via arc::PluginHandle for the
// production build. For the testing build, this function always returns
// NULL.
VirtualFileSystemInterface* GetFileSystem();

}  // namespace arc

#endif  // WRAP_FILE_WRAP_PRIVATE_H_
