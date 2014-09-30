// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMMON_OPTIONS_H_
#define COMMON_OPTIONS_H_

#include <string>
#include <vector>

#include "gtest/gtest_prod.h"

template <typename T> struct DefaultSingletonTraits;

namespace arc {

struct Options {
  static Options* GetInstance();

  static bool ParseBoolean(const char* str);

  void Reset();

  int GetMinStderrLogPriority() const {
    return min_stderr_log_priority_;
  }

  void ParseMinStderrLogPriority(const std::string& priority);

  // Controls the size of the Graphics3D/Image2D resource. These are specified
  // in DIPs.
  int app_height;
  int app_width;

  // Command to run.
  // Example commands are:
  //   1) Install an app and launch it
  //        install /path/to/my.apk ; shell am start $package
  //   2) Test an app
  //        install /path/to/my.apk ; install /path/to/test.apk ;
  //        shell am instrument -w
  //            my.example.package.test/android.test.InstrumentationTestRunner
  std::vector<std::string> command;

  // Initial country code for Android locale. This value should be ISO 3166-1
  // compliant two-letter upper-case characters. This value is optional and can
  // be empty.
  std::string country;

  // If true, enable adb support.
  bool enable_adb;

  // Whether to enable strace logging output.
  bool enable_arc_strace;

  // If true, the app will be outputting via the PPAPI compositor.
  bool enable_compositor;

  // If true, glGetError and glCheckFramebufferStatus will behave normally.
  // Otherwise glGetError always returns GL_NO_ERROR and
  // glCheckFramebufferStatus always returns GL_FRAMEBUFFER_COMPLETE.
  bool enable_gl_error_check;

  // If true, /storage/sdcard will be bound to external directory.
  bool enable_mount_external_directory;

  // The maximum rate (in frames per second) in which the SwapBuffers can be
  // called. This should only be used for GPU-heavy applications that are either
  // extremely janky or generate an uncomfortable amount of heat. Defaults to
  // 60, which means unlimited.
  // TODO(crbug.com/411538): Either remove this flag or document it in
  // external-developers.md.
  int fps_limit;

  // Indicates if HTML5 reports that we are rendering to a touchscreen.
  bool has_touchscreen;

  // 0 indicates no JDWP debugging, anything else indicates JDWP port
  // for debugging, and that we wait for a debugger.
  int jdwp_port;

  // Initial language code for Android locale. This value should be ISO 639-1
  // compliant two-letter lower-case characters. This must not be empty.
  std::string language;

  // If true, enable logging of asset and class accesses.
  bool log_load_progress;

  // ABI for NDK libraries.
  std::string ndk_abi;

  // Package name to assign to all loaded APK files.
  std::string package_name;

  // Services in Play Services that needs to be enabled seperated by space, e.g.
  // "gcm plus".
  std::string use_play_services;

  // If true, install GoogleContactsSyncAdapter.apk.
  bool use_google_contacts_sync_adapter;

  // User email of Chrome sign-in session.
  std::string user_email;

  // The lcd_density setting ARC should use.
  int android_density_dpi;

  // Track app window focus
  bool track_focus;

 private:
  friend struct DefaultSingletonTraits<Options>;
  FRIEND_TEST(OptionsTest, HandleFilterspecMessage);

  Options();
  ~Options();

  // The minimum log priority. Any log's priority is less than this value
  // will not be printed to stderr.
  int min_stderr_log_priority_;
};

}  // namespace arc

#endif  // COMMON_OPTIONS_H_
