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
// Checks if argv and envp are properly passed.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char* argv[], char* envp[]) {
  int i, envc;

  printf("argc=%d\n", argc);
  for (i = 0; i < argc; i++) {
    printf("%s\n", argv[i]);
  }
  if (argc < 2) {
    return 1;
  }
  if (strcmp(argv[1], "foobar"))
    return 2;
  puts("argv LGTM");

  for (envc = 0; envp[envc]; envc++) {}
  printf("envc=%d\n", envc);
  const char* ld_library_path_found = NULL;
  for (i = 0; i < envc; i++) {
    printf("%s\n", envp[i]);
    if (!strncmp(envp[i], "LD_LIBRARY_PATH=", strlen("LD_LIBRARY_PATH=")))
      ld_library_path_found = envp[i];
  }
  if (i < 1)
    return 3;
  if (!ld_library_path_found)
    return 4;
  puts("envp LGTM");

  if (!getenv("LD_LIBRARY_PATH"))
    return 5;
  if (getenv("NO_SUCH_ENV"))
    return 6;
  puts("getenv LGTM");

  puts("PASS");
  return 0;
}
