/*
 * Copyright (c) 2011 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include "ppapi/native_client/src/untrusted/irt_stub/ppapi_start.h"
/* ARC MOD BEGIN */
#if defined(USE_FPABI_SHIM)
/*
 * ARC is built with soft-fp, but PPAPI requires hard-fp. To fill the gap
 * we inject "shim" code here.
 */
#include "ppapi/native_client/src/untrusted/irt_stub/ppapi_fpabi_shim.h"

static int32_t shim_PPPInitializeModule(PP_Module module_id,
                                        PPB_GetInterface get_browser_intf) {
  __set_real_FpAbiShim_PPBGetInterface(get_browser_intf);
  return PPP_InitializeModule(module_id, &__FpAbiShim_PPBGetInterface);
}

static const struct PP_StartFunctions ppapi_app_start_callbacks = {
  shim_PPPInitializeModule,
  PPP_ShutdownModule,
  __FpAbiShim_PPPGetInterface,
};

#else
/* ARC MOD END */

/*
 * These are dangling references to functions that the application must define.
 */
static const struct PP_StartFunctions ppapi_app_start_callbacks = {
  PPP_InitializeModule,
  PPP_ShutdownModule,
  PPP_GetInterface
};
/* ARC MOD BEGIN */
#endif  /* USE_FPABI_SHIM */
/* ARC MOD END */

/*
 * The application's main (or the one supplied in this library) calls this
 * to start the PPAPI world.
 */
int PpapiPluginMain(void) {
  /* ARC MOD BEGIN */
#if defined(USE_FPABI_SHIM)
  __set_real_FpAbiShim_PPPGetInterface(PPP_GetInterface);
#endif  /* USE_FPABI_SHIM */
  /* ARC MOD END */
  return PpapiPluginStart(&ppapi_app_start_callbacks);
}
