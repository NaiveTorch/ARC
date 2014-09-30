#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generate shim code to adjust calling convention for floating point on ARM.

ARC is build in softfp mode, but Chrome's PPAPI interfaces are in hardfp.
This script generates the shim code to fill the gap.
"""

import sys

import idl_gen_wrapper
import idl_generator
import idl_option
import idl_parser


idl_option.Option('fpabishim', 'Name of the ABI shim file.',
                  default='ppapi_fpabi_shim.c')


class FpAbiShimGen(idl_gen_wrapper.WrapperGen):
  """Shim Generator to fill the soft-fp/hard-fp gap between on arm devices."""

  def __init__(self):
    super(FpAbiShimGen, self).__init__(
        'FpAbiShim', 'Floating Point Abi Shim Gen', 'fpabi',
        'Generate the floating point ABI shim.')

  def OwnHeaderFile(self):
    """Returns the header file that specifies the API of this wrapper."""
    return 'ppapi/native_client/src/untrusted/irt_stub/ppapi_fpabi_shim.h'

  def IsFloatingPointType(self, node, release):
    """Returns True if the node's type is a floating point type on the release.

    Here, a floating point type means a type that is passed via a floating
    point register on hard-fp ARM ABI.
    """
    if node.GetListOf('Array'):
      # If the type is an array, it is not passed via fp register on hard-fp
      # ARM.
      return False

    t = node.GetType(release)
    if not t:
      return False
    # Resolve typedef. Some types, such as PP_Time, are a synonym of a floating
    # point type.
    while t.IsA('Typedef'):
      t = t.GetType(release)
    return (t.IsA('Type') and
            t.GetName() in ('double_t', 'float_t', 'GLfloat', 'GLclampf'))

  def InterfaceVersionNeedsWrapping(self, iface, version):
    """Returns True if shim for ABI is needed for the interface.

    Here is the strategy:
    - If it is not PPB_ interface, we do not need a shim. It should be called
      from the nacl_helper at bootstrap of the plugin, and there is no ABI
      incompatibility on them.
    - If all methods in the interface do not have floating point parameters or
      return value, we do not need a shim.
    - Otherwise, we generate a shim for the interface. Note that a shim
      function will be generated even if the function does not have the
      floating point params or return value but some other functions in the
      same interface requires shim.
    """
    if not iface.GetName().startswith('PPB_'):
      # We are interested in PPB_ interfaces only.
      return False

    release = iface.GetRelease(version)
    for member in iface.GetListOf('Member'):
      # Check the return type.
      if self.IsFloatingPointType(member, release):
        return True

      # Check param types.
      for param in member.GetOneOf('Callspec').GetListOf('Param'):
        if self.IsFloatingPointType(param, release):
          return True
    # No floating point params or return value is found.
    return False

  def GenerateWrapperForPPBMethod(self, iface, member):
    """Generates a shim function code.

    The generated shim code looks something like:

    static void FpAbiShim_M20_PPB_Some_PPAPI_FunctionName(
        PP_Resource resrouce, ArgType arg) {
        const struct PPB_Some_PPAPI_Struct *iface =
            FpAbiShim_WrapperInfo_PPB_Some_PPAPI_Struct.real_iface;
        __attribute__((pcs("aapcs-vfp"))) void (*temp_fp)(
            PP_Resource resource, ArgType arg) =
            (__attribute__((pcs("aapcs-vfp"))) void (*)(
                PP_Resource resource, ArgType arg))iface->FunctionName;
        temp_fp(resource, arg);
    }
    """
    function_prefix = self.WrapperMethodPrefix(iface.node, iface.release)
    return_type, name, arrayspec, callspec = self.cgen.GetComponents(
        member, iface.release, 'store')
    temp_fp_name = 'temp_fp'

    template = '\n'.join([
        'static %(signature)s {',
        '  const struct %(interface)s *iface =',
        '      %(wrapper_struct)s.real_iface;',
        '  __attribute__((pcs("aapcs-vfp"))) %(var_decl)s =',
        '      (__attribute__((pcs("aapcs-vfp"))) %(cast)s)iface->%(member)s;',
        '  %(return_prefix)s%(temp_fp_name)s(%(args)s);',
        '}'])
    return template % {
        'signature': self.cgen.GetSignature(
            member, iface.release, 'store', function_prefix, False),
        'interface': iface.struct_name,
        'wrapper_struct': self.GetWrapperInfoName(iface),
        'var_decl': self.cgen.Compose(
            return_type, name, arrayspec, callspec, prefix=temp_fp_name,
            func_as_ptr=True, include_name=False, unsized_as_ptr=False),
        'cast': self.cgen.Compose(
            return_type, name, arrayspec, callspec, prefix='',
            func_as_ptr=True, include_name=False, unsized_as_ptr=False),
        'member': member.GetName(),
        'return_prefix': 'return ' if return_type != 'void' else '',
        'temp_fp_name': temp_fp_name,
        'args': ', '.join(name for _, name, _, _ in callspec),
    } + '\n\n'  # Add an empty line between the next function.

  def GenerateWrapperInterfaces(self, iface_releases, out):
    """Generates a struct definition for PPAPI.

    The generated struct looks something like:

    static const struct PPB_SomePPAPIStructName
        FpAbiShim_Wrappers_PPB_SomePPAPIStructName = {
        .PPAPIFuncName1 = &FpAbiShim_M20_PPB_SomePPAPIStructName_FuncName1,
        .PPAPIFuncName2 = &FpAbiShim_M20_PPB_SomePPAPIStructName_FuncName2,
        .PPAPIFuncName3 = &FpAbiShim_M20_PPB_SomePPAPIStructName_FuncName3,
            :
    };
    """
    for iface in iface_releases:
      if not iface.needs_wrapping:
        out.Write('/* Not generating wrapper interface for %s */\n\n' %
                  iface.struct_name)
        continue

      lines = []
      struct_template = (
          'static const struct %(struct)s %(prefix)s_Wrappers_%(struct)s = {')
      lines.append(struct_template % {
          'struct': iface.struct_name,
          'prefix': self.wrapper_prefix,
      })

      method_prefix = self.WrapperMethodPrefix(iface.node, iface.release)
      for member in iface.node.GetListOf('Member'):
        if not member.InReleases([iface.release]):
          continue
        line_template = '    .%(member)s = &%(method_prefix)s%(member)s,'
        lines.append(line_template % {
            'member': member.GetName(),
            'method_prefix': method_prefix,
        })
      lines.append('};')
      out.Write('\n'.join(lines))
      out.Write('\n\n')  # Add an empty line between the next struct.

  def GenerateRange(self, ast, releases, options):
    # Note: Generator code in Chrome tree has an (invisible) issue that it
    # outputs uncompilable source code. It is because some function pointer
    # type needs to be versionized, but the generator doesn't it properly.
    # Invocation of GetUniqueReleases() fixes the problem. It is also
    # (implicitly) done in AST verification (in idl_c_header.CheckTypedefs).
    # In chromium tree, it is not the actual problem, because the verification
    # function is always invoked in regular use cases.
    for filenode in ast.GetListOf('File'):
      for node in filenode.GetListOf('Typedef'):
        node.GetUniqueReleases(releases)

    self.SetOutputFile(idl_option.GetOption('fpabishim'))
    return super(FpAbiShimGen, self).GenerateRange(ast, releases, options)


# Instantiate the generator here, globally. It registers itself as a part of
# Generator, so that idl_generator.Generator.Run() properly handles the
# ABI shim generation.
fpabishimgen = FpAbiShimGen()


def main():
  filenames = idl_option.ParseOptions(sys.argv[1:])
  ast = idl_parser.ParseFiles(filenames)
  assert not ast.errors, ast.errors
  return idl_generator.Generator.Run(ast)


if __name__ == '__main__':
  main()
