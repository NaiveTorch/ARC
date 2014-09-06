// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMMON_MATRIX_H_
#define COMMON_MATRIX_H_

#include <math.h>
#include <stddef.h>

namespace arc {

class Vector;

static const float kPi = M_PI;
static const float kRadiansPerDegree = kPi / 180.0f;

// 4x4 floating point matrix.
class Matrix {
 public:
  static const int kN = 4;  // N as in NxN matrix.
  static const int kEntries = kN * kN;

  Matrix() {
    AssignIdentity();
  }

  Matrix(float m00, float m01, float m02, float m03,
         float m10, float m11, float m12, float m13,
         float m20, float m21, float m22, float m23,
         float m30, float m31, float m32, float m33);

  void Set(int row, int col, float value) {
    // The entries are stored in column-major order.
    entries_[col * kN + row] = value;
  }

  float Get(int row, int col) const {
    // The entries are stored in column-major order.
    return entries_[col * kN + row];
  }

  void Inverse();

  void Transpose();

  void AssignIdentity();

  void AssignMatrixMultiply(const Matrix& a, const Matrix& b);

  const Matrix& operator *=(const Matrix& b) {
    AssignMatrixMultiply(*this, b);
    return *this;
  }

  float* GetColumnMajorArray(float (&entries)[kEntries]) const;
  float* GetColumnMajorArray(float* entries, size_t count) const;

  static Matrix GenerateColumnMajor(const float* entries);

  static Matrix GenerateScale(const Vector& v);

  static Matrix GenerateTranslation(const Vector& v);

  static Matrix GenerateRotationByDegrees(float degrees,
                                          const Vector& v);

  static Matrix GeneratePerspective(float left, float right,
                                    float bottom, float top,
                                    float z_near, float z_far);

  static Matrix GenerateOrthographic(float left, float right,
                                     float bottom, float top,
                                     float z_near, float z_far);

 private:
  float entries_[kEntries];
};

}  // namespace arc

#endif  // COMMON_MATRIX_H_
