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

#include <stdio.h>

#include "resolve_parent_sym_test.h"

int answer_in_main();
int answer_in_first();

int run_test_in_second() {
  puts("run_test_in_second");
  if (answer_in_main() != MAIN_ANSWER)
    return 0;
  if (answer_in_first() != FIRST_ANSWER)
    return 0;
  return SECOND_ANSWER;
}
