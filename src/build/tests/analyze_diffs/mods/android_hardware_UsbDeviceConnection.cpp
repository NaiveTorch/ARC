/*
 * Copyright (C) 2011 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#define LOG_TAG "UsbDeviceConnectionJNI"

#include "utils/Log.h"

#include "jni.h"
#include "JNIHelp.h"
#include "android_runtime/AndroidRuntime.h"

#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

/* ARC MOD BEGIN */
#include "common/danger.h"
/* ARC MOD END */

using namespace android;

static jfieldID field_context;

struct usb_device* get_device_from_object(JNIEnv* env, jobject connection)
{
    return (struct usb_device*)env->GetIntField(connection, field_context);
}

static jboolean
android_hardware_UsbDeviceConnection_open(JNIEnv *env, jobject thiz, jstring deviceName,
        jobject fileDescriptor)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return false;
    /* ARC MOD END */
}

static void
android_hardware_UsbDeviceConnection_close(JNIEnv *env, jobject thiz)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    /* ARC MOD END */
}

static jint
android_hardware_UsbDeviceConnection_get_fd(JNIEnv *env, jobject thiz)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return -1;
    /* ARC MOD END */
}

static jbyteArray
android_hardware_UsbDeviceConnection_get_desc(JNIEnv *env, jobject thiz)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return NULL;
    /* ARC MOD END */
}

static jboolean
android_hardware_UsbDeviceConnection_claim_interface(JNIEnv *env, jobject thiz,
        int interfaceID, jboolean force)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return false;
    /* ARC MOD END */
}

static jint
android_hardware_UsbDeviceConnection_release_interface(JNIEnv *env, jobject thiz, int interfaceID)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return -1;
    /* ARC MOD END */
}

static jint
android_hardware_UsbDeviceConnection_control_request(JNIEnv *env, jobject thiz,
        jint requestType, jint request, jint value, jint index,
        jbyteArray buffer, jint length, jint timeout)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return -1;
    /* ARC MOD END */
}

static jint
android_hardware_UsbDeviceConnection_bulk_request(JNIEnv *env, jobject thiz,
        jint endpoint, jbyteArray buffer, jint length, jint timeout)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return -1;
    /* ARC MOD END */
}

static jobject
android_hardware_UsbDeviceConnection_request_wait(JNIEnv *env, jobject thiz)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return NULL;
    /* ARC MOD END */
}

static jstring
android_hardware_UsbDeviceConnection_get_serial(JNIEnv *env, jobject thiz)
{
    /* ARC MOD BEGIN */
    NOT_IMPLEMENTED();
    return NULL;
    /* ARC MOD END */
}

static JNINativeMethod method_table[] = {
    {"native_open",             "(Ljava/lang/String;Ljava/io/FileDescriptor;)Z",
                                        (void *)android_hardware_UsbDeviceConnection_open},
    {"native_close",            "()V",  (void *)android_hardware_UsbDeviceConnection_close},
    {"native_get_fd",           "()I",  (void *)android_hardware_UsbDeviceConnection_get_fd},
    {"native_get_desc",         "()[B", (void *)android_hardware_UsbDeviceConnection_get_desc},
    {"native_claim_interface",  "(IZ)Z",(void *)android_hardware_UsbDeviceConnection_claim_interface},
    {"native_release_interface","(I)Z", (void *)android_hardware_UsbDeviceConnection_release_interface},
    {"native_control_request",  "(IIII[BII)I",
                                        (void *)android_hardware_UsbDeviceConnection_control_request},
    {"native_bulk_request",     "(I[BII)I",
                                        (void *)android_hardware_UsbDeviceConnection_bulk_request},
    {"native_request_wait",             "()Landroid/hardware/usb/UsbRequest;",
                                        (void *)android_hardware_UsbDeviceConnection_request_wait},
    { "native_get_serial",      "()Ljava/lang/String;",
                                        (void*)android_hardware_UsbDeviceConnection_get_serial },
};

int register_android_hardware_UsbDeviceConnection(JNIEnv *env)
{
    jclass clazz = env->FindClass("android/hardware/usb/UsbDeviceConnection");
    if (clazz == NULL) {
        ALOGE("Can't find android/hardware/usb/UsbDeviceConnection");
        return -1;
    }
    field_context = env->GetFieldID(clazz, "mNativeContext", "I");
    if (field_context == NULL) {
        ALOGE("Can't find UsbDeviceConnection.mNativeContext");
        return -1;
    }

    return AndroidRuntime::registerNativeMethods(env, "android/hardware/usb/UsbDeviceConnection",
            method_table, NELEM(method_table));
}
