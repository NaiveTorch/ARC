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
// Checks if stdio and malloc work.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
  printf("Hello, world!\n");

  // malloc should work as well.
  char* buf = malloc(256);
  strcpy(buf, "malloc");
  fprintf(stderr, "%s+fprintf+stderr\n", buf);

  puts("PASS");
  return 0;
}
