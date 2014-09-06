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
// Define NEXT_CTOR_FUNC_NEEDS_IRT_QUERY_MARKER
//

#ifndef _ANDROID_BIONIC_LIBC_PRIVATE_IRT_QUERY_MARKER_H
#define _ANDROID_BIONIC_LIBC_PRIVATE_IRT_QUERY_MARKER_H

// The loader or crtbegin pass __nacl_irt_query to the function
// immediately after this magic value. will We will set this value
// using __attribute__((section)) because __attribute__((constructor))
// cannot be used for variables. See bionic/linker/linker.h for why we
// need to pass __nacl_irt_query in this way.
#define NEXT_CTOR_FUNC_NEEDS_IRT_QUERY_MARKER (void*)-2

#endif  // _ANDROID_BIONIC_LIBC_PRIVATE_IRT_QUERY_MARKER_H
