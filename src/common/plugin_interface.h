// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Abstract interface to a pepper plugin.  We are intentionally avoiding
// using anything from the pp namespace in hopes of keeping a clean
// abstraction layer between Android code and Chrome Pepper code.

#ifndef COMMON_PLUGIN_INTERFACE_H_
#define COMMON_PLUGIN_INTERFACE_H_

#include <sys/types.h>

#include <string>
#include <vector>

#include "common/options.h"

// Use uint16 instead of uint8 since Dalvik and Chrome disagree on how to
// encode utf-8.
typedef uint16_t MessageCharType;

namespace arc {

class InputManagerInterface;
class VirtualFileSystemInterface;

class RendererInterface {
 public:
  struct RenderParams {
    // Width of display in actual pixels.
    int width;
    // Width of display in actual pixels.
    int height;
    // Device scale from device independent pixels to actual pixels.
    float device_render_to_view_pixels;
    // Like crx_render_to_view_pixels, controls the size of the
    // Graphics3D/Image2D resource. See also common/options.h.
    float crx_render_to_view_pixels;
  };
  virtual ~RendererInterface() {}

  // Get the plugin's render characteristics.
  virtual void GetRenderParams(RenderParams* params) const = 0;
};

class SWRendererInterface {
 public:
  enum BitmapFormat {
    RGBA8,
    BGRA8
  };
  struct SWRenderParams {
    // Image format that will be presented to Chrome in the software
    // renderer.
    BitmapFormat format;
    // Bytes per pixel in software renderer.
    int stride;
    // Total size in bytes of software rendered image.
    int size;
  };
  virtual ~SWRendererInterface() {}

  // Render the given bitmap.  The bitmap data must match
  // the render parameters returned by GetRenderParams.  The
  // memory of bitmap will be copied by the time this function
  // returns, so it can be invalidated immediately after.
  virtual void RenderBitmap(void* bitmap) = 0;

  // Get the plugin's render characteristics.
  virtual void GetSWRenderParams(SWRenderParams* params) = 0;
};

// Opaque type of GPU context pointers.
struct ContextGPU;

namespace compositor {
class CompositorInterface;
}  // namespace compositor

class GPURendererInterface {
 public:
  virtual ~GPURendererInterface() {}

  virtual void CreateAttribs(
      int red_size, int green_size, int blue_size, int alpha_size,
      int depth_size, int stencil_size, std::vector<int32_t>& attribs) = 0;
  virtual ContextGPU* CreateContextGPU(const std::vector<int32_t>& attribs,
                                       ContextGPU* shared_context) = 0;
  virtual void ShareContextGPU(void* context, void* shared_context) = 0;
  virtual bool BindGraphics3D(ContextGPU* context) = 0;
  virtual void DestroyContextGPU(void* context) = 0;
  // TODO(kmixter): Remove this once we have separate contexts
  // and surfaces.
  virtual bool ResizeGraphics3D(ContextGPU* context,
                                int width,
                                int height) = 0;
  virtual void CallMakeCurrent(void* context) = 0;
  // If a pending SwapBuffers call is in flight, block until it is serviced.
  virtual void WaitForSwapBuffers() = 0;
  // Check whether a SwapBuffers callback is pending.
  virtual bool IsSwapBuffersOutstanding() = 0;
  virtual bool SwapBuffersGraphics3D(ContextGPU* context) = 0;
  virtual compositor::CompositorInterface* GetCompositor() = 0;
};

class AudioManagerInterface {
 public:
  struct AudioParams {
    int sample_rate;
    // Number of samples per audio frame that the plugin will request.
    int sample_frame_count;
    int num_channels;
    int bytes_per_sample;
  };
  virtual ~AudioManagerInterface() {}

  // Get the plugin's audio output characteristics.
  virtual bool GetAudioOutParams(AudioParams* params) = 0;

  // Signals to plugin that audio output is in standby mode.
  virtual bool SetAudioOutStandby() = 0;

  // Gets the estimated latency in ms of plugin audio output.
  virtual uint32_t GetAudioOutLatency() = 0;

  // Buffers audio data for later rendering.
  virtual size_t WriteAudioOutData(const void* buffer, size_t size) = 0;

  // Opens the audio input device. Returns false on failure.
  virtual bool OpenAudioIn() = 0;

  // Closes the audio input device.
  virtual void CloseAudioIn() = 0;

  // Get the plugin's audio input characteristics.
  virtual bool GetAudioInParams(AudioParams* params) = 0;

  // Set the plugin's audio input sampling rate.
  virtual uint32_t SetAudioInSampleRate(uint32_t sample_rate) = 0;

  // Signals to plugin that audio input is in standby mode.
  virtual bool SetAudioInStandby() = 0;

  // Reads audio data from the input device.
  virtual size_t ReadAudioInData(void* buffer, size_t size) = 0;
};


// YUV Component Equivalencies:
// - YUV == YCbCr / YVU == YCrCb
// YUV Format Layouts:
// - YV12 = 8-bit 1x1 Y -> 8-bit 2x2 V -> 8-bit 2x2 U
// - I420 = 8-bit 1x1 Y -> 8-bit 2x2 U -> 8-bit 2x2 V
// - NV12 = 8-bit 1x1 Y -> Interleaved (8-bit 2x2 U, 8-bit 2x2 V) pairs
// - NV21 = 8-bit 1x1 Y -> Interleaved (8-bit 2x2 V, 8-bit 2x2 U) pairs
//
enum VideoFrameFormat {
  ARC_VIDEOFRAME_FORMAT_UNKNOWN = 0,
  ARC_VIDEOFRAME_FORMAT_YV21 = 1,
  ARC_VIDEOFRAME_FORMAT_NV21 = ARC_VIDEOFRAME_FORMAT_YV21,
  ARC_VIDEOFRAME_FORMAT_I420 = 2,
  ARC_VIDEOFRAME_FORMAT_BGRA = 3,
  ARC_VIDEOFRAME_FORMAT_RGBA = 4,
  ARC_VIDEOFRAME_FORMAT_RGB  = 5,
  ARC_VIDEOFRAME_FORMAT_YV12 = 6,
  ARC_VIDEOFRAME_FORMAT_NV12 = 7
};

class CameraManagerInterface {
 public:
  virtual ~CameraManagerInterface() {}

  // Opens the device and set it to standby to capture frames.
  virtual bool OpenVideoIn() = 0;

  // Closes the device.
  virtual void CloseVideoIn() = 0;

  // Capture one video frame. This must be called before ReadVideoInData and
  // must be released using ReleaseFrame. If this function returns false,
  // frame data was not read so ReadVideoInData and ReleaseFrame must not
  // be called. If the function is successful, |*frame_nsecs| will be updated
  // with the frame timestamp in nanoseconds since the start of the process
  // using a monotonic clock.
  virtual bool CaptureFrame(int64_t* frame_nsecs) = 0;

  // Reads video data from the last captured frame, performing any necessary
  // scaling and format conversions. Should only be called if CaptureFrame
  // returned true.
  virtual size_t ReadVideoInData(uint8_t* buffer, uint32_t width,
                                 uint32_t height,
                                 VideoFrameFormat format) = 0;

  // Releases the last captured frame. Should only be called if CaptureFrame
  // returned true.
  virtual void ReleaseFrame() = 0;
};


// Defines the set of supported video profiles.
enum VideoProfile {
  ARC_VIDEOPROFILE_H264BASELINE = 0,
  ARC_VIDEOPROFILE_H264MAIN = 1,
  ARC_VIDEOPROFILE_H264EXTENDED = 2,
  ARC_VIDEOPROFILE_H264HIGH = 3,
  ARC_VIDEOPROFILE_H264HIGH10 = 4,
  ARC_VIDEOPROFILE_H264HIGH422 = 5,
  ARC_VIDEOPROFILE_H264HIGH444PREDICTIVE = 6,
  ARC_VIDEOPROFILE_H264SCALABLEBASELINE = 7,
  ARC_VIDEOPROFILE_H264SCALABLEHIGH = 8,
  ARC_VIDEOPROFILE_H264STEREOHIGH = 9,
  ARC_VIDEOPROFILE_H264MULTIVIEWHIGH = 10,
  ARC_VIDEOPROFILE_VP8MAIN = 11,
  ARC_VIDEOPROFILE_VP9MAIN = 12,
};

class VideoDecoderInterface {
 public:
  virtual ~VideoDecoderInterface() {}

  // Accelerated video decoding callback interface. The decoder invokes these
  // functions sequentially, from a single thread, without recursion
  // from a decoder call.
  struct Client {
    virtual ~Client() {}

    // Invoked when the decoder has been disabled. No more callback functions
    // will be invoked for the corresponding decoder.
    // The implementer is responsible for deleting this Client instance.
    virtual void OnDecoderDisabled() = 0;

    // Invoked after encountering an error during decoding. After this callback
    // all calls except Reset() and Destroy() will be ignored.
    virtual void ReportError(
        const char* message, bool is_corrupt_stream) = 0;

    // Invoked after successful decoder creation, and then whenever
    // the user code should provide more data through Decode() call.
    // Last Decode's buffer can be reused at this point.
    virtual void NeedMoreData() = 0;

    // Invoked when a video frame has been decoded as a texture.
    // The client has to invoke RecycleTexture() once the texture has been
    // rendered, so that it can be reused for another frame. Resetting or
    // destroying the decoder will automatically recycle all textures.
    // The pixel format of the texture is GL_RGBA.
    virtual void OnTextureReady(
        uint32_t decode_id, uint32_t texture_target, uint32_t texture_id,
        uint32_t width, uint32_t height) = 0;

    // Invoked once Flush() call has completed processing all data.
    virtual void FlushCompleted() = 0;

    // Invoked once Reset() call has completed discarding all data.
    virtual void ResetCompleted() = 0;
  };

  typedef void (*DestroyCallbackFunc)(void* param);

  // Checks whether video decoding is supported for a given profile.
  virtual bool CanDecode(ContextGPU* context, VideoProfile profile) = 0;

  // Starts a video decoding process. Takes over ownership of GL context.
  // Only one video decoding process is allowed per GPU context. Returns
  // non-zero decoder id that should be used with the other methods.
  // Invokes |destroy_func| and passes |destroy_param| when context
  // is no longer needed. Fills out |tracking_handle| for use with
  // SharedObjectTracker.
  virtual uint32_t StartDecoding(
      ContextGPU* context, VideoProfile profile, Client* client,
      int* tracking_handle, DestroyCallbackFunc destroy_func,
      void* destroy_param) = 0;

  // Permanently disables processing on the given video decoder.
  // All further calls with the same |decoder_id| will fail in debug builds.
  // Invokes OnDecoderDisabled() once done disabling.
  // The actual decoder instance will be destroyed once all extra
  // references have been freed through SharedObjectTracker.
  virtual void Disable(uint32_t decoder_id) = 0;

  // Flushes all pending data. Will invoke FlushCompleted() once done.
  virtual void Flush(uint32_t decoder_id) = 0;

  // Resets all pending data. Cancels all pending operations and
  // invokes ResetCompleted().
  virtual void Reset(
      uint32_t decoder_id, std::vector<uint32_t> unused_textures) = 0;

  // Requests decoding of video data. This call can be made only after
  // receiving NeedMoreData() callback. Data buffer should not be modified
  // until the next NeedMoreData() callback is received.
  virtual void Decode(
      uint32_t decoder_id, uint32_t decode_id,
      const void* data, uint32_t len) = 0;

  // Requests the decoder to provide a texture through OnTextureReady()
  // callback. Only one request can be outstanding at any given time.
  virtual void ProvideTexture(uint32_t decoder_id) = 0;

  // Returns the texture that was earlier provided with OnTextureReady().
  virtual void RecycleTexture(
      uint32_t decoder_id, uint32_t texture_id) = 0;
};


typedef void* (*ThreadCallbackFunc)(void* p);

class AndroidMessageHandler {
 public:
  virtual ~AndroidMessageHandler() {}

  // This function will be called on main thread, so it should return
  // as soon as possible.
  virtual void OnMessage(const MessageCharType* message, size_t length) = 0;
};

class ArcMessageBridgeMessageSender {
 public:
  virtual ~ArcMessageBridgeMessageSender() {}

  virtual void PostMessage(const MessageCharType* message, size_t length) = 0;
  virtual void StartListening(const MessageCharType* name_space,
                              size_t length) = 0;
  virtual void StopListening(const MessageCharType* name_space,
                             size_t length) = 0;
  virtual void StartInterceptMessageForTest(const MessageCharType* name_space,
                                            size_t length) = 0;
  virtual void StopInterceptMessageForTest(const MessageCharType* name_space,
                                           size_t length) = 0;
};


// Miscellaneous
class PluginUtilInterface {
 public:
  virtual ~PluginUtilInterface() {}

  // Run |func| on the renderer thread with the given argument.  This will block
  // on the non-renderer thread until the renderer thread runs |func| and
  // returns.  The return value of |func| is passed back as the return value of
  // RunOnRendererThread.
  virtual void* RunOnRendererThread(ThreadCallbackFunc func, void* arg) = 0;

  virtual void SetTimeZone(const char* timezone) = 0;
  virtual bool IsMainThread() = 0;
  virtual bool IsRendererThread() = 0;

  // Sets JavScript message handler and returns message sender interface. Caller
  // must free |handler| and returned object.
  virtual ArcMessageBridgeMessageSender* InitializeArcMessageBridge(
      AndroidMessageHandler* handler) = 0;
  virtual int RunAndWaitForChildPlugin(const char* const argv[],
                                       const char* preopened_fd_args[],
                                       const char* preopened_fd_names[]) = 0;
  virtual void HistogramShortTime(const std::string& name, int64_t time_ms) = 0;
  virtual void HistogramLongTime(const std::string& name, int64_t time_ms) = 0;
  virtual void HistogramBoolean(const std::string& name, bool value) = 0;
  virtual void HistogramEnumeration(const std::string& name,
                                    int value, int bounds) = 0;

  // Start shut down of environment.
  virtual void ShutDown() = 0;
};

class PluginInterface {
 public:
  virtual RendererInterface* GetRenderer() = 0;
  virtual GPURendererInterface* GetGPURenderer() = 0;
  virtual SWRendererInterface* GetSWRenderer() = 0;
  virtual VirtualFileSystemInterface* GetVirtualFileSystem() = 0;
  virtual InputManagerInterface* GetInputManager() = 0;
  virtual AudioManagerInterface* GetAudioManager() = 0;
  virtual CameraManagerInterface* GetCameraManager() = 0;
  virtual VideoDecoderInterface* GetVideoDecoder() = 0;
  virtual PluginUtilInterface* GetPluginUtil() = 0;

 protected:
  PluginInterface();
  virtual ~PluginInterface() = 0;
};

}  // namespace arc

#endif  // COMMON_PLUGIN_INTERFACE_H_
