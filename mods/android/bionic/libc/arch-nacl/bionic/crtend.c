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
// The terminator of ctors, dtors, and eh_frame. All shared objects
// and executables should link this as the last object.
//

#include <stdint.h>

// This cannot be static because _init in crtbegin.c will use this to
// iterate .ctors in reverse order.
//
// Note that we do not define them as arrays which have a single
// element because of the reason mentioned in crtbegin_so.c.
__attribute__((used, section(".ctors"), visibility("hidden")))
void (*const __CTOR_END__)(void) = 0;
__attribute__((used, section(".dtors")))
static void (*const __DTOR_END__)(void) = 0;
__attribute__ ((used, section (".eh_frame")))
static const uint32_t __FRAME_END__[1] = { 0 };
