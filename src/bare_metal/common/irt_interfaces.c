// ARC MOD TRACK "third_party/native_client/src/untrusted/irt/irt_interfaces.c"
// ARC MOD IGNORE
// Everything in this directory are ephemeral and we will add no new
// features. We do not need to sync with Chrome code.
// TODO(crbug.com/364632): Remove this directory.
/*
 * Copyright (c) 2012 The Native Client Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

// ARC MOD BEGIN
// Add stdio.h and stdlib.h.
#include <stdio.h>
#include <stdlib.h>
// ARC MOD END
#include <string.h>

// ARC MOD BEGIN
// Replace #include.
#include "bare_metal/common/bare_metal_irt.h"
#include "bare_metal/common/irt.h"
#include "bare_metal/common/irt_core.h"
#include "bare_metal/common/irt_dev.h"
#include "bare_metal/common/irt_interfaces.h"

#define NACL_ARRAY_SIZE(a) ((int)(sizeof(a) / sizeof(a[0])))
// ARC MOD END

static int file_access_filter(void) {
  // ARC MOD BEGIN
  // Always enable file access for ARC unittests.
  return 1;
  // ARC MOD END
}

// ARC MOD BEGIN
// Remove an unnecessary filter for list_mappings.
// ARC MOD END

static int non_pnacl_filter(void) {
  // ARC MOD BEGIN
  // Bare Metal is not PNaCl always.
  return -1;
  // ARC MOD END
}

static const struct nacl_irt_interface irt_interfaces[] = {
  { NACL_IRT_BASIC_v0_1, &nacl_irt_basic, sizeof(nacl_irt_basic), NULL },
  /*
   * "irt-fdio" is disabled under PNaCl because file descriptors in
   * general are not exposed in PNaCl's in-browser ABI (since
   * open_resource() is also disabled under PNaCl).  "irt-fdio" is
   * only exposed under PNaCl via the "dev" query string since writing
   * to stdout/stderr is useful for debugging.
   */
  { NACL_IRT_FDIO_v0_1, &nacl_irt_fdio, sizeof(nacl_irt_fdio),
    non_pnacl_filter },
  { NACL_IRT_DEV_FDIO_v0_1, &nacl_irt_fdio, sizeof(nacl_irt_fdio), NULL },
  // ARC MOD BEGIN
  // We do not provide NACL_IRT_DEV_FDIO_v0_3 interface.
  // { NACL_IRT_DEV_FDIO_v0_3, &nacl_irt_dev_fdio, sizeof(nacl_irt_dev_fdio),
  //   file_access_filter },
  // ARC MOD END
  /*
   * "irt-filename" is made available to non-PNaCl NaCl apps only for
   * compatibility, because existing nexes abort on startup if
   * "irt-filename" is not available.
   */
  { NACL_IRT_FILENAME_v0_1, &nacl_irt_filename, sizeof(nacl_irt_filename),
    non_pnacl_filter },
  { NACL_IRT_DEV_FILENAME_v0_2, &nacl_irt_dev_filename,
    sizeof(nacl_irt_dev_filename), file_access_filter },
  // ARC MOD BEGIN
  // This file had NACL_IRT_MEMORY_v0_1 and v0_2 here, but we do not
  // need the deprecated interfaces.
  // ARC MOD END
  { NACL_IRT_MEMORY_v0_3, &nacl_irt_memory, sizeof(nacl_irt_memory), NULL },
  /*
   * "irt-dyncode" is not supported under PNaCl because dynamically
   * loading architecture-specific native code is not portable.
   */
  // ARC MOD BEGIN
  // Bare Metal does not need dyncode interfaces.
  // { NACL_IRT_DYNCODE_v0_1, &nacl_irt_dyncode, sizeof(nacl_irt_dyncode),
  //  non_pnacl_filter },
  // ARC MOD END
  { NACL_IRT_THREAD_v0_1, &nacl_irt_thread, sizeof(nacl_irt_thread), NULL },
  { NACL_IRT_FUTEX_v0_1, &nacl_irt_futex, sizeof(nacl_irt_futex), NULL },
  /*
   * "irt-mutex", "irt-cond" and "irt-sem" are deprecated and
   * superseded by the "irt-futex" interface, and so are disabled
   * under PNaCl.  See:
   * https://code.google.com/p/nativeclient/issues/detail?id=3484
   */
  // ARC MOD BEGIN
  // Bare Metal does not provide deprecated mutex interfaces.
  //
  // { NACL_IRT_MUTEX_v0_1, &nacl_irt_mutex, sizeof(nacl_irt_mutex), NULL },
  // { NACL_IRT_COND_v0_1, &nacl_irt_cond, sizeof(nacl_irt_cond), NULL },
  // { NACL_IRT_SEM_v0_1, &nacl_irt_sem, sizeof(nacl_irt_sem), NULL },
  // ARC MOD END
  { NACL_IRT_TLS_v0_1, &nacl_irt_tls, sizeof(nacl_irt_tls), NULL },
  /*
   * "irt-blockhook" is deprecated.  It was provided for implementing
   * thread suspension for conservative garbage collection, but this
   * is probably not a portable use case under PNaCl, so this
   * interface is disabled under PNaCl.  See:
   * https://code.google.com/p/nativeclient/issues/detail?id=3539
   */
  // ARC MOD BEGIN
  // TODO(crbug.com/266627): Enable them.
  // { NACL_IRT_BLOCKHOOK_v0_1, &nacl_irt_blockhook, sizeof(nacl_irt_blockhook),
  //   NULL },
  // { NACL_IRT_RESOURCE_OPEN_v0_1, &nacl_irt_resource_open,
  //   sizeof(nacl_irt_resource_open), non_pnacl_filter },
  // ARC MOD END
  { NACL_IRT_RANDOM_v0_1, &nacl_irt_random, sizeof(nacl_irt_random), NULL },
  { NACL_IRT_CLOCK_v0_1, &nacl_irt_clock, sizeof(nacl_irt_clock), NULL },
  // ARC MOD BEGIN
  // TODO(crbug.com/266627): Enable them.
  // { NACL_IRT_DEV_GETPID_v0_1, &nacl_irt_dev_getpid,
  //   sizeof(nacl_irt_dev_getpid), NULL },
  // /*
  //  * "irt-exception-handling" is not supported under PNaCl because it
  //  * exposes non-portable, architecture-specific register state.  See:
  //  * https://code.google.com/p/nativeclient/issues/detail?id=3444
  //  */
  // { NACL_IRT_EXCEPTION_HANDLING_v0_1, &nacl_irt_exception_handling,
  //   sizeof(nacl_irt_exception_handling), NULL },
  // { NACL_IRT_DEV_LIST_MAPPINGS_v0_1, &nacl_irt_dev_list_mappings,
  //   sizeof(nacl_irt_dev_list_mappings), list_mappings_filter },

  // Add bare_metal_irt_debugger.
  { BARE_METAL_IRT_DEBUGGER_v0_1, &bare_metal_irt_debugger,
    sizeof(bare_metal_irt_debugger), NULL },
  // ARC MOD END
};

size_t nacl_irt_query_list(const char *interface_ident,
                           void *table, size_t tablesize,
                           const struct nacl_irt_interface *available,
                           size_t available_size) {
  unsigned available_count = available_size / sizeof(*available);
  unsigned i;
  for (i = 0; i < available_count; ++i) {
    if (0 == strcmp(interface_ident, available[i].name)) {
      if (NULL == available[i].filter || available[i].filter()) {
        const size_t size = available[i].size;
        if (size <= tablesize) {
          memcpy(table, available[i].table, size);
          return size;
        }
      }
      break;
    }
  }
  // ARC MOD BEGIN
  // Add a warning.
  // TODO(crbug.com/266627): Remove this.
  fprintf(stderr, "bm_loader: Unknown interface_ident: %s\n",
          interface_ident);
  // ARC MOD END
  return 0;
}

size_t nacl_irt_query_core(const char *interface_ident,
                           void *table, size_t tablesize) {
  return nacl_irt_query_list(interface_ident, table, tablesize,
                             irt_interfaces, sizeof(irt_interfaces));
}
