/*
 * Copyright 2014 The Chromium Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#ifndef PPAPI_NATIVE_CLIENT_SRC_UNTRUSTED_IRT_STUB_PPAPI_FPABI_SHIM_H_
#define PPAPI_NATIVE_CLIENT_SRC_UNTRUSTED_IRT_STUB_PPAPI_FPABI_SHIM_H_

#include "ppapi/c/ppb.h"

/* Defines the interface exposed by the generated wrapper code. */

typedef PPB_GetInterface PPP_GetInterface_Type;

void __set_real_FpAbiShim_PPBGetInterface(PPB_GetInterface real);
void __set_real_FpAbiShim_PPPGetInterface(PPP_GetInterface_Type real);

const void *__FpAbiShim_PPBGetInterface(const char *name);
const void *__FpAbiShim_PPPGetInterface(const char *name);

struct __FpAbiShimWrapperInfo {
  const char *iface_macro;
  const void *wrapped_iface;
  const void *real_iface;
};

#endif  /* PPAPI_NATIVE_CLIENT_SRC_UNTRUSTED_IRT_STUB_PPAPI_FPABI_SHIM_H_ */
