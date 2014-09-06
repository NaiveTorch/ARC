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
// Define nacl_abi_timeval and its conversion functions.
//
// Note that nacl-glibc's timeval is as same as NaCl IRT's. In
// bionic, tv_sec and tv_usec is 32bit values so we need conversion.
//

#ifndef _NACL_TIMEVAL_H
#define _NACL_TIMEVAL_H

#include <stdint.h>
#include <sys/cdefs.h>
#include <sys/time.h>

__BEGIN_DECLS

struct nacl_abi_timeval {
  int64_t tv_sec;
  int64_t tv_usec;
};

void __nacl_abi_timeval_to_timeval(const struct nacl_abi_timeval *nacl_timeval,
                                   struct timeval *timeval);

void __timeval_to_nacl_abi_timeval(const struct timeval *timeval,
                                   struct nacl_abi_timeval *nacl_timeval);

__END_DECLS

#endif  // _NACL_TIMEVAL_H
