/* ARC MOD TRACK "third_party/android/system/core/init/property_service.c" */
/*
 * Copyright (C) 2007 The Android Open Source Project
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

/* ARC MOD BEGIN */
/* TODO(crbug.com/354536): Implement a compatible property service for ARC.
 *
 * Implementing a proper service will mean revisiting the mods to this file,
 * which are just intended to get the basic system property code working.
 *
 * For ARC, we take a copy of the init version of property_service.c, and
 * strip it down to the minimum of functionality we need -- the call to write a
 * property (and related code).
 *
 * On a stock android device, the property service is one of the details handled
 * by the init code on boot, and is something available through a socket
 * interface. Normally the property service is the only process that as a
 * writable mmap() of the properties file. All other processes mmap() a
 * read-only copy of the memory.
 *
 * In addition to writes, the property service normally also handles update
 * notifications, but this is currently disabled here.
 */
/* ARC MOD END */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <ctype.h>
#include <fcntl.h>
#include <stdarg.h>
#include <dirent.h>
#include <limits.h>
#include <errno.h>
/* ARC MOD BEGIN */
#include <stdbool.h>
#include <pthread.h>

#include <private/libc_logging.h>
/* ARC MOD END */

#define _REALLY_INCLUDE_SYS__SYSTEM_PROPERTIES_H_
#include <sys/_system_properties.h>

/* ARC MOD BEGIN */
// Normally this service writes errors out as a kernel level log.
// Map the calls to be a libc error message instead since that is where this
// code is being run.
#define ERROR(...) __libc_format_log(ANDROID_LOG_ERROR, "libc", __VA_ARGS__)

static int persistent_properties_loaded = 0;
static pthread_mutex_t set_mutex_ = PTHREAD_MUTEX_INITIALIZER;


// ARC does not use selinux, so we stub this call out to do nothing.
static void selinux_reload_policy() {}

// For now, we do not support property change notifications, so stub this call
// out to do nothing.
static void property_changed(const char* name, const char* value) {}
/* ARC MOD END */

static void write_persistent_property(const char *name, const char *value)
{
  /* ARC MOD BEGIN */
  // TODO(crbug.com/354523): Implement persistent properties in ARC
  // correctly, delete this stub as needed to have the call go to the intended
  // implementation.
  /* ARC MOD END */
}

static bool is_legal_property_name(const char* name, size_t namelen)
{
    size_t i;
    bool previous_was_dot = false;
    if (namelen >= PROP_NAME_MAX) return false;
    if (namelen < 1) return false;
    if (name[0] == '.') return false;
    if (name[namelen - 1] == '.') return false;

    /* Only allow alphanumeric, plus '.', '-', or '_' */
    /* Don't allow ".." to appear in a property name */
    for (i = 0; i < namelen; i++) {
        if (name[i] == '.') {
            if (previous_was_dot == true) return false;
            previous_was_dot = true;
            continue;
        }
        previous_was_dot = false;
        if (name[i] == '_' || name[i] == '-') continue;
        if (name[i] >= 'a' && name[i] <= 'z') continue;
        if (name[i] >= 'A' && name[i] <= 'Z') continue;
        if (name[i] >= '0' && name[i] <= '9') continue;
        return false;
    }

    return true;
}

/* ARC MOD BEGIN */
// We make property_set static since it is otherwise exposed by the move from
// the init code.
static
/* ARC MOD END */
int property_set(const char *name, const char *value)
{
    prop_info *pi;
    int ret;

    size_t namelen = strlen(name);
    size_t valuelen = strlen(value);

    if (!is_legal_property_name(name, namelen)) return -1;
    if (valuelen >= PROP_VALUE_MAX) return -1;

    pi = (prop_info*) __system_property_find(name);

    if(pi != 0) {
        /* ro.* properties may NEVER be modified once set */
        if(!strncmp(name, "ro.", 3)) return -1;

        __system_property_update(pi, value, valuelen);
    } else {
        ret = __system_property_add(name, namelen, value, valuelen);
        if (ret < 0) {
            ERROR("Failed to set '%s'='%s'\n", name, value);
            return ret;
        }
    }
    /* If name starts with "net." treat as a DNS property. */
    if (strncmp("net.", name, strlen("net.")) == 0)  {
        if (strcmp("net.change", name) == 0) {
            return 0;
        }
       /*
        * The 'net.change' property is a special property used track when any
        * 'net.*' property name is updated. It is _ONLY_ updated here. Its value
        * contains the last updated 'net.*' property.
        */
        property_set("net.change", name);
    } else if (persistent_properties_loaded &&
            strncmp("persist.", name, strlen("persist.")) == 0) {
        /*
         * Don't write properties to disk until after we have read all default properties
         * to prevent them from being overwritten by default values.
         */
        write_persistent_property(name, value);
    } else if (strcmp("selinux.reload_policy", name) == 0 &&
               strcmp("1", value) == 0) {
        selinux_reload_policy();
    }
    property_changed(name, value);
    return 0;
}

/* ARC MOD BEGIN */
__attribute__ ((visibility ("hidden")))
int __system_property_service_set(const char * name, const char* value) {
  // The underlying property code is built assuming multiple concurrent readers
  // but only one concurrent writer. Enforce the single writer with a mutex.
  pthread_mutex_lock(&set_mutex_);
  int retval = property_set(name, value);
  pthread_mutex_unlock(&set_mutex_);
  return retval;
}
/* ARC MOD END */
