#!/usr/bin/env python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from build_options import OPTIONS


def get_android_static_library_deps():
  deps = [
      'libandroid.a',
      'libandroid_runtime.a',
      'libandroid_servers.a',
      'libandroid_servers_arc.a',
      'libandroid_servers_vibrator.a',
      'libaudioflinger.a',
      'libaudioutils.a',  # used by libmedia
      'libbinder.a',
      'libbinder_driver.a',
      'libbootanimation.a',
      'libcamera_client.a',
      'libcamera_metadata.a',  # used by libcameraservice
      'libcameraservice.a',
      'libcommon_time_client.a',  # used by audioflinger
      'libconnectivitymanager.a',
      'libcorkscrew.a',
      'libcpustats.a',
      'libcrypto_static.a',
      'libcutils.a',
      'libdrmframeworkcommon.a',
      'libdrmserver.a',
      'libeffects.a',
      'libemoji.a',
      'libetc1.a',
      'libexpat.a',
      'libFLAC.a',  # used by libstagefright
      'libft2.a',  # used by libskia
      'libgabi++.a',
      'libgccdemangle.a',
      'libgif.a',  # used by libskia
      'libgui.a',
      'libhardware.a',
      'libharfbuzz_ng.a',
      'libicui18n.a',
      'libicuuc.a',
      'libinput.a',
      'libinputservice.a',
      'libjpeg_static.a',
      'liblogcat.a',
      'liblog_fake.a',
      'libmedia.a',
      'libmedia_helper.a',  # used by audioflinger
      'libmediaplayerservice.a',
      'libmemtrack.a',
      'libnbaio.a',  # used by audioflinger
      'libndk_libandroid.a',
      'libndk_libandroid_runtime.a',
      'libndk_libEGL.a',
      'libndk_libGLESv1_CM.a',
      'libndk_libGLESv2.a',
      'libndk_libOpenSLES.a',
      'libndk_libjnigraphics.a',
      'libndk_liblog.a',
      'libndk_libnativehelper.a',
      'libndk_libz.a',
      'libOpenMAXAL.a',
      'libopensles_helper.a',  # used by libOpenMAXAL
      'libOpenSLES.a',  # used by libOpenMAXAL
      'libOpenSLESUT.a',  # used by libOpenMAXAL
      'libpng.a',  # used by libskia
      'libpowermanager.a',
      'libsafe_iop.a',
      'libscheduling_policy.a',  # used by audioflinger
      'libsensorservice.a',
      'libsfntly.a',  # used by libskia
      'libskia.a',
      'libsonivox.a',
      'libspeexresampler.a',  # used by libaudioutils
      'libsqlite3_android.a',
      'libsqlite.a',
      'libssl_static.a',
      'libstagefright.a',
      'libstagefright_amrnb_common.a',  # used by libmedia_jni
      'libstagefright_color_conversion.a',  # used by libstagefright
      'libstagefright_enc_common.a',
      'libstagefright_foundation.a',
      'libstagefright_httplive.a',  # used by libstagefright
      'libstagefright_id3.a',  # used by libstagefright
      'libstagefright_matroska.a',  # used by libstagefright
      'libstagefright_mpeg2ts.a',  # used by libstagefright
      'libstagefright_nuplayer.a',  # used by libmediaplayerservice
      'libstagefright_omx.a',
      'libstagefright_rtsp.a',  # used by libmediaplayerservice
      'libstagefright_timedtext.a',  # used by libstagefright
      'libstagefright_wfd.a',  # used by libmediaplayerservice
      'libstagefright_yuv.a',
      'libsync.a',  # used by HW composer
      'libui.a',
      'libunwind.a',
      'libvorbisidec.a',  # used by libstagefright
      'libvpx.a',  # used by libstagefright
      'libwebm.a',  # used by libstagefright
      'libwebp-decode.a',  # used by libskia
      'libwebp-encode.a',  # used by libskia
      'libwilhelm.a',  # used by libOpenMAXAL
      'libyuv_static.a',
      'libz.a']

  if OPTIONS.enable_emugl():
    deps.append('libEGL.a')
    deps.append('libGLESv1_CM.a')
  else:
    deps.append('libegl.a')
    deps.append('libgles.a')
    deps.append('libgralloc.a')

  if not OPTIONS.disable_hwui():
    deps.append('libhwui.a')

  if OPTIONS.enable_aacenc():
    deps.append('libstagefright_aacenc.a')

  return deps
