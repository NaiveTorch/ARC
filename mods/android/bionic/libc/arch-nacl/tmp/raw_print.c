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
// Utility functions to output strings on NaCl.
//
// As functions in this file use NaCl syscall directly, they work even
// when NaCl IRT and/or libc are not ready.
//
// TODO(crbug.com/243244): Remove this file once bionic becomes ready.
//

#if __STDC_VERSION__ < 199901L
#error this file is C99 only
#endif

#if defined(BARE_METAL_BIONIC)
#include <irt_syscalls.h>
#include <sys/syscall.h>
#endif
#include <limits.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

static void nacl_syscall_write(int fd, const void *buf, int count) {
#if defined(BARE_METAL_BIONIC)
  syscall(__NR_write, fd, buf, count);
#else
  static const int NACL_sys_write = 13;
  int (* syscall_write)(int desc, void const *buf, int count);
  static const int kTrampolinesStartAddress = 0x10000;
  syscall_write = (int (*)(int desc, void const *buf, int count))(
      kTrampolinesStartAddress + NACL_sys_write * 32);
  syscall_write(fd, buf, count);
#endif
}

__attribute__ ((visibility("hidden")))
void print_str(const char* s) {
  int cnt = 0;
  const char* p;
  for (p = s; *p; p++)
    cnt++;
  static const int kStderrFd = 2;
  nacl_syscall_write(kStderrFd, s, cnt);
}

__attribute__ ((visibility("hidden")))
void print_str_array(char* const* a) {
  int i;
  for (i = 0; a[i]; i++) {
    if (i) print_str(" ");
    print_str(a[i]);
  }
}

// We use long instead of int for all integer values in this file
// because we want to handle pointer values even on x86-64. It is safe
// to pass 32 bit int to 64 bit long on x86-64 because they usually
// fill zeros to the upper 32 bits of data.
static char* stringify_int(long v, char* p) {
  int is_negative = 0;
  *p = '\0';
  if (v < 0) {
    if (v == LONG_MIN) {
      --p;
      // The last digit is 8 for both 32bit and 64bit long.
      *p = '8';
      // This heavily depends on C99's division.
      v /= 10;
    }
    v = -v;
    is_negative = 1;
  }
  do {
    --p;
    *p = v % 10 + '0';
    v /= 10;
  } while (v);
  if (is_negative)
    *--p = '-';
  return p;
}

__attribute__ ((visibility("hidden")))
void print_int(long v) {
  char buf[32];
  print_str(stringify_int(v, buf + sizeof(buf) - 1));
}

static char* stringify_hex(long v, char* p) {
  int is_negative = 0;
  int c;
  *p = '\0';
  if (v < 0) {
    if (v == LONG_MIN) {
      --p;
      *p = '0';
      // This heavily depends on C99's division.
      v /= 16;
    }
    v = -v;
    is_negative = 1;
  }
  do {
    --p;
    c = v % 16;
    *p = c < 10 ? c + '0' : c - 10 + 'A';
    v /= 16;
  } while (v);
  *--p = 'x';
  *--p = '0';
  if (is_negative)
    *--p = '-';
  return p;
}

__attribute__ ((visibility("hidden")))
void print_hex(long v) {
  char buf[32];
  print_str(stringify_hex(v, buf + sizeof(buf) - 1));
}

__attribute__ ((visibility("hidden")))
void print_format(const char* fmt, ...) {
  static const char kOverflowMsg[] = " *** OVERFLOW! ***\n";
  char buf[300] = {0};
  const size_t kMaxFormattedStringSize = sizeof(buf) - sizeof(kOverflowMsg);
  char* outp = buf;
  const char* inp;
  va_list ap;
  int is_overflow = 0;

  va_start(ap, fmt);
  for (inp = fmt; *inp && (outp - buf) < kMaxFormattedStringSize; inp++) {
    if (*inp != '%') {
      *outp++ = *inp;
      if (outp - buf >= kMaxFormattedStringSize) {
        is_overflow = 1;
        break;
      }
      continue;
    }

    char cur_buf[32];
    char* cur_p;
    switch (*++inp) {
      case 'd':
        // This is unsafe if we pass more than 6 integer values to
        // this function on x86-64, because it starts using stack.
        // You need to cast to long in the call site for such cases.
        cur_p = stringify_int(va_arg(ap, long), cur_buf + sizeof(cur_buf) - 1);
        break;
      case 'x':
        cur_p = stringify_hex(va_arg(ap, long), cur_buf + sizeof(cur_buf) - 1);
        break;
      case 's':
        cur_p = va_arg(ap, char*);
        break;
      default:
        print_str("unknown format!\n");
        abort();
    }

    size_t len = strlen(cur_p);
    if (outp + len - buf >= kMaxFormattedStringSize) {
      is_overflow = 1;
      break;
    }
    strcat(buf, cur_p);
    outp += len;
  }
  va_end(ap);

  if (strlen(buf) > kMaxFormattedStringSize) {
    print_str(buf);
    if (is_overflow)
      print_str(kOverflowMsg);
    // This should not happen.
    abort();
  }
  if (is_overflow)
    strcat(buf, kOverflowMsg);
  print_str(buf);
}
