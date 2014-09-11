// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMMON_VECTOR_H_
#define COMMON_VECTOR_H_

#include <math.h>
#include <limits>

namespace arc {

class Matrix;

class Vector {
 public:
  static const size_t kEntries = 4;
  Vector() {
    entries_[0] = entries_[1] = entries_[2] = entries_[3] = 0.0f;
  }

  Vector(float v1, float v2, float v3, float v4) {
    entries_[0] = v1;
    entries_[1] = v2;
    entries_[2] = v3;
    entries_[3] = v4;
  }

  void Set(int index, float value) {
    entries_[index] = value;
  }

  float Get(int index) const {
    return entries_[index];
  }

  float GetDotProduct(const Vector& v) const;

  float GetLengthSquared() const {
    return GetDotProduct(*this);
  }

  float GetLength() const {
    return sqrt(GetLengthSquared());
  }

  void Scale(float v) {
    entries_[0] *= v;
    entries_[1] *= v;
    entries_[2] *= v;
    entries_[3] *= v;
  }

  void Normalize() {
    Scale(1.0f / GetLength());
  }

  float* GetFloatArray(float (&data)[4]) const {
    for (size_t i = 0; i < kEntries; i++)
      data[i] = entries_[i];
    return data;
  };

  void AssignMatrixMultiply(const Matrix& a, const Vector& b);

  void AssignLinearMapping(const float* params, size_t count);
  void AssignLinearMapping(const int32_t* params, size_t count);
  void AssignLinearMapping(const int16_t* params, size_t count);
  void AssignLinearMapping(const int8_t* params, size_t count);
  void AssignLinearMapping(const uint16_t* params, size_t count);
  void AssignLinearMapping(const uint8_t* params, size_t count);

  void GetLinearMapping(float* params, size_t count) const;
  void GetLinearMapping(int32_t* params, size_t count) const;

  // TODO(lpique) Merge with Haroon's Clamp()
  void Clamp(float min, float max);

 private:
  template <typename T>
  void AssignLinearMappingHelper(const T* params, size_t count);
  template <typename T>
  void GetLinearMappingHelper(T* params, size_t count) const;

  float entries_[kEntries];
};

}  // namespace arc

#endif  // COMMON_VECTOR_H_
