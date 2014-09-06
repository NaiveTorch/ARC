// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Interface to Chrome from Android code.

#ifndef COMMON_PLUGIN_HANDLE_H_
#define COMMON_PLUGIN_HANDLE_H_

#include "common/alog.h"
#include "common/plugin_interface.h"
#include "common/private/minimal_base.h"

namespace arc {

class PluginHandle {
 public:
  PluginHandle() {}
  ~PluginHandle() {}

  RendererInterface* GetRenderer() const {
    return GetPlugin()->GetRenderer();
  }
  SWRendererInterface* GetSWRenderer() const {
    return GetPlugin()->GetSWRenderer();
  }
  GPURendererInterface* GetGPURenderer() const {
    return GetPlugin()->GetGPURenderer();
  }
  VirtualFileSystemInterface* GetVirtualFileSystem() const {
    return GetPlugin()->GetVirtualFileSystem();
  }
  InputManagerInterface* GetInputManager() const {
    return GetPlugin()->GetInputManager();
  }
  AudioManagerInterface* GetAudioManager() const {
    return GetPlugin()->GetAudioManager();
  }
  CameraManagerInterface* GetCameraManager() const {
    return GetPlugin()->GetCameraManager();
  }
  VideoDecoderInterface* GetVideoDecoder() const {
    return GetPlugin()->GetVideoDecoder();
  }
  PluginUtilInterface* GetPluginUtil() const {
    return GetPlugin()->GetPluginUtil();
  }

  // Sets the current plugin for the process. This function must be called
  // from the main thread only once before the first pthread_create() call
  // is made.
  static void SetPlugin(PluginInterface* plugin);

 private:
  friend class AppInstanceInitTest;
  friend class ChildPluginInstanceTest;
  friend class InstanceDispatcherInitTest;
  friend class MockPlugin;

  PluginInterface* GetPlugin() const {
    ALOG_ASSERT(plugin_);
    // A mutex lock is not necessary here since |plugin_| is set by the main
    // thread before the first pthread_create() call is made. It is ensured
    // that a non-main thread can see non-NULL |plugin_| value because
    // pthread_create() call to create the thread itself is a memory barrier.
    return plugin_;
  }

  // For testing. Do not call.
  static void UnsetPlugin();

  static PluginInterface* plugin_;

  COMMON_DISALLOW_COPY_AND_ASSIGN(PluginHandle);
};

}  // namespace arc
#endif  // COMMON_PLUGIN_HANDLE_H_
