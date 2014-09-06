#ifndef IOTA_H
#define IOTA_H

#include <numeric>

//iota definition used in unit test
template <typename _It, typename _Tp>
void __iota(_It __first, _It __last, _Tp __val) {
/* ARC MOD BEGIN */
// To work with GCC >= 4.7, we can't call iota() even the STL extension is
// enabled. The reason is that the extra unqualified lookups are disabled by
// default on GCC >= 4.7.(http://gcc.gnu.org/gcc-4.7/porting_to.html)
#if defined (STLPORT) && !defined (_STLP_NO_EXTENSIONS) && 0
/* ARC MOD END */
  iota(__first, __last, __val);
#else
  while (__first != __last) {
    *__first++ = __val++;
  }
#endif
}

#endif
