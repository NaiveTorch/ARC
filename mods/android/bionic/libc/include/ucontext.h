/* Copyright (c) 2014 The Chromium Authors. All rights reserved. */

// Defines ucontext_t for use by libunwind. Ideally this should become a part
// of Native Client. In fact, this appears to exist in nacl-glibc,
// but not in nacl-newlib. That means nacl-arm builds do not have the header.
// However, if we decide against support of signals in Native Client,
// this may need to become a part of libunwind itself as NaCl apps should
// be able to use libunwind without Bionic.

#ifndef _UCONTEXT_H_
#define _UCONTEXT_H_

// Machine includes expect stack_t definition.
#include <signal.h>

#ifdef __x86_64__
#include <machine/ucontext64.h>
#else
#include <machine/ucontext.h>
#endif

#endif /* _UCONTEXT_H_ */
