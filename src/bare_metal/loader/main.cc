// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// The dynamic linking loader for bare metal ARC.
//

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

#include "bare_metal/common/loader.h"
#include "bare_metal/common/log.h"

static void ShowHelpAndExit(const char* arg0) {
  fprintf(stderr, "Usage: %s [-E env_key=env_value] <binary> ...\n", arg0);
  exit(1);
}

static void ParseCommandLineFlags(int* argc_inout, char*** argv_inout) {
  int argc = *argc_inout;
  char** argv = *argv_inout;
  const char* arg0 = argv[0];
  argc--;
  argv++;

  while (argv[0] && argv[0][0] == '-') {
    if (!strcmp(argv[0], "-E")) {
      argc--;
      argv++;
      // We pass all environment variables in host to the loaded
      // binaries. This can be a security issue, but we are not sure
      // as of now.
      // TODO(crbug.com/266627): Think about this.
      CHECK(!putenv(argv[0]), "putenv failed: %s", argv[0]);
    } else {
      fprintf(stderr, "Unknown command line flag: %s\n", argv[0]);
      ShowHelpAndExit(arg0);
    }
    argc--;
    argv++;
  }
  if (argc <= 0)
    ShowHelpAndExit(arg0);

  *argc_inout = argc;
  *argv_inout = argv;
}

int main(int argc, char* argv[]) {
  ParseCommandLineFlags(&argc, &argv);

  bare_metal::Loader* loader = bare_metal::Loader::Create(argv[0]);
  int fd = open(argv[0], O_RDONLY);
  CHECK(fd >= 0, "%s: Cannot open file", argv[0]);
  loader->Load(fd);
  close(fd);

  loader->Run(argc, argv);
  delete loader;
}
