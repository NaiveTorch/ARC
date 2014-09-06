// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/matrix.h"

#include <string.h>

#include "common/alog.h"
#include "common/vector.h"

namespace arc {

Matrix::Matrix(float m00, float m01, float m02, float m03,
               float m10, float m11, float m12, float m13,
               float m20, float m21, float m22, float m23,
               float m30, float m31, float m32, float m33) {
  Set(0, 0, m00);
  Set(0, 1, m01);
  Set(0, 2, m02);
  Set(0, 3, m03);
  Set(1, 0, m10);
  Set(1, 1, m11);
  Set(1, 2, m12);
  Set(1, 3, m13);
  Set(2, 0, m20);
  Set(2, 1, m21);
  Set(2, 2, m22);
  Set(2, 3, m23);
  Set(3, 0, m30);
  Set(3, 1, m31);
  Set(3, 2, m32);
  Set(3, 3, m33);
}

void Matrix::AssignIdentity() {
  memset(&entries_, 0, sizeof(entries_));
  Set(0, 0, 1.f);
  Set(1, 1, 1.f);
  Set(2, 2, 1.f);
  Set(3, 3, 1.f);
}

void Matrix::Transpose() {
  for (int i = 0; i < kN; ++i) {
    for (int j = i + 1; j < kN; ++j) {
      const float temp = Get(i, j);
      Set(i, j, Get(j, i));
      Set(j, i, temp);
    }
  }
}

void Matrix::Inverse() {
  float inv[kEntries];
  inv[0] = entries_[5]  * entries_[10] * entries_[15] -
           entries_[5]  * entries_[11] * entries_[14] -
           entries_[9]  * entries_[6]  * entries_[15] +
           entries_[9]  * entries_[7]  * entries_[14] +
           entries_[13] * entries_[6]  * entries_[11] -
           entries_[13] * entries_[7]  * entries_[10];

  inv[4] = -entries_[4]  * entries_[10] * entries_[15] +
            entries_[4]  * entries_[11] * entries_[14] +
            entries_[8]  * entries_[6]  * entries_[15] -
            entries_[8]  * entries_[7]  * entries_[14] -
            entries_[12] * entries_[6]  * entries_[11] +
            entries_[12] * entries_[7]  * entries_[10];

  inv[8] = entries_[4]  * entries_[9] * entries_[15] -
           entries_[4]  * entries_[11] * entries_[13] -
           entries_[8]  * entries_[5] * entries_[15] +
           entries_[8]  * entries_[7] * entries_[13] +
           entries_[12] * entries_[5] * entries_[11] -
           entries_[12] * entries_[7] * entries_[9];

  inv[12] = -entries_[4]  * entries_[9] * entries_[14] +
             entries_[4]  * entries_[10] * entries_[13] +
             entries_[8]  * entries_[5] * entries_[14] -
             entries_[8]  * entries_[6] * entries_[13] -
             entries_[12] * entries_[5] * entries_[10] +
             entries_[12] * entries_[6] * entries_[9];

  inv[1] = -entries_[1]  * entries_[10] * entries_[15] +
            entries_[1]  * entries_[11] * entries_[14] +
            entries_[9]  * entries_[2] * entries_[15] -
            entries_[9]  * entries_[3] * entries_[14] -
            entries_[13] * entries_[2] * entries_[11] +
            entries_[13] * entries_[3] * entries_[10];

  inv[5] = entries_[0]  * entries_[10] * entries_[15] -
           entries_[0]  * entries_[11] * entries_[14] -
           entries_[8]  * entries_[2] * entries_[15] +
           entries_[8]  * entries_[3] * entries_[14] +
           entries_[12] * entries_[2] * entries_[11] -
           entries_[12] * entries_[3] * entries_[10];

  inv[9] = -entries_[0]  * entries_[9] * entries_[15] +
            entries_[0]  * entries_[11] * entries_[13] +
            entries_[8]  * entries_[1] * entries_[15] -
            entries_[8]  * entries_[3] * entries_[13] -
            entries_[12] * entries_[1] * entries_[11] +
            entries_[12] * entries_[3] * entries_[9];

  inv[13] = entries_[0]  * entries_[9] * entries_[14] -
            entries_[0]  * entries_[10] * entries_[13] -
            entries_[8]  * entries_[1] * entries_[14] +
            entries_[8]  * entries_[2] * entries_[13] +
            entries_[12] * entries_[1] * entries_[10] -
            entries_[12] * entries_[2] * entries_[9];

  inv[2] = entries_[1]  * entries_[6] * entries_[15] -
           entries_[1]  * entries_[7] * entries_[14] -
           entries_[5]  * entries_[2] * entries_[15] +
           entries_[5]  * entries_[3] * entries_[14] +
           entries_[13] * entries_[2] * entries_[7] -
           entries_[13] * entries_[3] * entries_[6];

  inv[6] = -entries_[0]  * entries_[6] * entries_[15] +
            entries_[0]  * entries_[7] * entries_[14] +
            entries_[4]  * entries_[2] * entries_[15] -
            entries_[4]  * entries_[3] * entries_[14] -
            entries_[12] * entries_[2] * entries_[7] +
            entries_[12] * entries_[3] * entries_[6];

  inv[10] = entries_[0]  * entries_[5] * entries_[15] -
            entries_[0]  * entries_[7] * entries_[13] -
            entries_[4]  * entries_[1] * entries_[15] +
            entries_[4]  * entries_[3] * entries_[13] +
            entries_[12] * entries_[1] * entries_[7] -
            entries_[12] * entries_[3] * entries_[5];

  inv[14] = -entries_[0]  * entries_[5] * entries_[14] +
             entries_[0]  * entries_[6] * entries_[13] +
             entries_[4]  * entries_[1] * entries_[14] -
             entries_[4]  * entries_[2] * entries_[13] -
             entries_[12] * entries_[1] * entries_[6] +
             entries_[12] * entries_[2] * entries_[5];

  inv[3] = -entries_[1] * entries_[6] * entries_[11] +
            entries_[1] * entries_[7] * entries_[10] +
            entries_[5] * entries_[2] * entries_[11] -
            entries_[5] * entries_[3] * entries_[10] -
            entries_[9] * entries_[2] * entries_[7] +
            entries_[9] * entries_[3] * entries_[6];

  inv[7] = entries_[0] * entries_[6] * entries_[11] -
           entries_[0] * entries_[7] * entries_[10] -
           entries_[4] * entries_[2] * entries_[11] +
           entries_[4] * entries_[3] * entries_[10] +
           entries_[8] * entries_[2] * entries_[7] -
           entries_[8] * entries_[3] * entries_[6];

  inv[11] = -entries_[0] * entries_[5] * entries_[11] +
             entries_[0] * entries_[7] * entries_[9] +
             entries_[4] * entries_[1] * entries_[11] -
             entries_[4] * entries_[3] * entries_[9] -
             entries_[8] * entries_[1] * entries_[7] +
             entries_[8] * entries_[3] * entries_[5];

  inv[15] = entries_[0] * entries_[5] * entries_[10] -
            entries_[0] * entries_[6] * entries_[9] -
            entries_[4] * entries_[1] * entries_[10] +
            entries_[4] * entries_[2] * entries_[9] +
            entries_[8] * entries_[1] * entries_[6] -
            entries_[8] * entries_[2] * entries_[5];

  float det = entries_[0] * inv[0] + entries_[1] * inv[4]
            + entries_[2] * inv[8] + entries_[3] * inv[12];

  LOG_ALWAYS_FATAL_IF(det == 0.f);
  if (det != 0.f) {
    det = 1.0f / det;
    for (int i = 0; i < kEntries; ++i) {
      entries_[i] = inv[i] * det;
    }
  }
}

void Matrix::AssignMatrixMultiply(const Matrix& a, const Matrix& b) {
  // We need a separate copy of the result since we cannot assume that
  // this->entries_ is different from a's and b's entries.
  Matrix result;
  for (int a_row = 0; a_row < kN; ++a_row) {
    for (int b_col = 0; b_col < kN; ++b_col) {
      float dp = 0.0f;
      for (int k = 0; k < kN; ++k)
        dp += a.Get(a_row, k) * b.Get(k, b_col);
      result.Set(a_row, b_col, dp);
    }
  }
  *this = result;
}

Matrix Matrix::GenerateColumnMajor(const float* entries) {
  // It's safe to memcpy because entries are stored in column-major order.
  Matrix result;
  memcpy(result.entries_, entries, sizeof(result.entries_));
  return result;
}

float* Matrix::GetColumnMajorArray(float (&entries)[kEntries]) const {
  return GetColumnMajorArray(entries, kEntries);
}

float* Matrix::GetColumnMajorArray(float* entries, size_t count) const {
  // It's safe to memcpy because entries are stored in column-major order.
  memcpy(entries, entries_, count * sizeof(entries[0]));
  return entries;
}

Matrix Matrix::GeneratePerspective(float left, float right,
                                   float bottom, float top,
                                   float z_near, float z_far) {
  LOG_ALWAYS_FATAL_IF(left == right);
  LOG_ALWAYS_FATAL_IF(top == bottom);
  LOG_ALWAYS_FATAL_IF(z_near == z_far);

  // See http://www.songho.ca/opengl/gl_projectionmatrix.html.
  return Matrix((2.f * z_near) / (right - left),
                0.0f,
                (right + left) / (right - left),
                0.0f,

                0.0f,
                (2.f * z_near) / (top - bottom),
                (top + bottom) / (top - bottom),
                0.0f,

                0.0f,
                0.0f,
                -(z_far + z_near) / (z_far - z_near),
                (-2.0f * z_far * z_near) / (z_far - z_near),

                0.0f,
                0.0f,
                -1.0f,
                0.0f);
}

Matrix Matrix::GenerateOrthographic(float left, float right,
                                    float bottom, float top,
                                    float z_near, float z_far) {
  LOG_ALWAYS_FATAL_IF(left == right);
  LOG_ALWAYS_FATAL_IF(top == bottom);
  LOG_ALWAYS_FATAL_IF(z_near == z_far);

  // See http://www.songho.ca/opengl/gl_projectionmatrix.html.
  return Matrix(2.0f / (right - left),
                0.0f,
                0.0f,
                -(right + left) / (right - left),
                0.0f,
                2.0f / (top - bottom),
                0.0f,
                -(top + bottom) / (top - bottom),
                0.0f,
                0.0f,
                -2.0f / (z_far - z_near),
                -(z_far + z_near) / (z_far - z_near),
                0.0f,
                0.0f,
                0.0f,
                1.0f);
}

Matrix Matrix::GenerateScale(const Vector& v) {
  Matrix m;
  for (int i = 0; i < kN; ++i) {
    m.Set(i, i, v.Get(i));
  }
  return m;
}

Matrix Matrix::GenerateTranslation(const Vector& v) {
  Matrix m;
  for (int i = 0; i < kN; ++i) {
    m.Set(i, 3, v.Get(i));
  }
  return m;
}

Matrix Matrix::GenerateRotationByDegrees(float degrees,
                                         const Vector& v) {
  Vector w = v;
  w.Normalize();
  // See http://mathworld.wolfram.com/RodriguesRotationFormula.html or
  // http://www.manpagez.com/man/3/glRotatef/ for formulas.
  const float theta = degrees * kRadiansPerDegree;
  const float sin_t = sin(theta);
  const float cos_t = cos(theta);
  const float x_cos_t = 1.0f - cos_t;
  const float wx = w.Get(0);
  const float wy = w.Get(1);
  const float wz = w.Get(2);

  return Matrix(cos_t + wx * wx * x_cos_t,
                wx * wy * x_cos_t - wz * sin_t,
                wy * sin_t + wx * wz * x_cos_t,
                0.0f,
                wz * sin_t + wx * wy * x_cos_t,
                cos_t + wy * wy * x_cos_t,
                -wx * sin_t + wy * wz * x_cos_t,
                0.0f,
                -wy * sin_t + wx * wz * x_cos_t,
                wx * sin_t + wy * wz * x_cos_t,
                cos_t + wz * wz * x_cos_t,
                0.0f,
                0.0f,
                0.0f,
                0.0f,
                1.0f);
}

}  // namespace arc
