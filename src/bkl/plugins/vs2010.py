#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2011-2012 Vaclav Slavik
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
#  IN THE SOFTWARE.
#

import uuid
import types
import os.path
import codecs
from xml.sax.saxutils import escape, quoteattr

import bkl.compilers
import bkl.expr
import bkl.error
from bkl.api import Toolset, Property
from bkl.vartypes import PathType
from bkl.utils import OrderedDict
from bkl.io import OutputFile, EOL_WINDOWS

# TODO: Move this somewhere else, where it could be reused.
# TODO: make this model-visible type with validation (for user-settable GUIDs)
NAMESPACE_PRJ = uuid.UUID("{D9BD5916-F055-4D77-8C69-9448E02BF433}")

def GUID(namespace, solution, data):
    """
    Generates GUID in given namespace, for given solution (bkl project), with
    given data (typically, target ID).
    """
    g = uuid.uuid5(namespace, '%s/%s' % (str(solution), str(data)))
    return "{%s}" % str(g).upper()


class Node(object):
    def __init__(self, name, **kwargs):
        self.name = name
        self.attrs = OrderedDict()
        self.children = []
        self.attrs.update(kwargs)

    def __setitem__(self, key, value):
        self.attrs[key] = value

    def add(self, *args, **kwargs):
        """
        Add a child to this node. There are several ways of invoking add():

        The argument may be another node:
        >>> n.add(Node("foo"))

        Or it may be key-value pair, where the value is bkl.expr.Expr or any Python
        value convertible to string:
        >>> n.add("ProjectGuid", "{31DC1570-67C5-40FD-9130-C5F57BAEBA88}")
        >>> n.add("LinkIncremental", target["vs-incremental-link"])

        Or it can take the same arguments that Node constructor takes:
        >>> n.add("ImportGroup", Label="PropertySheets")
        """
        assert len(args) > 0
        arg0 = args[0]
        if len(args) == 1:
            if isinstance(arg0, Node):
                self.children.append((arg0.name, arg0))
                return
            elif isinstance(arg0, types.StringType):
                self.children.append((arg0, Node(arg0, **kwargs)))
                return
        elif len(args) == 2:
            if isinstance(arg0, types.StringType) and len(kwargs) == 0:
                    self.children.append((arg0, args[1]))
                    return
        assert 0, "add() is confused: what are you trying to do?"

    def has_children(self):
        return len(self.children) > 0


class VS2010ExprFormatter(bkl.expr.Formatter):
    list_sep = ";"
    def reference(self, e):
        assert False, "All references should be expanded in VS output"


XML_HEADER = """\
<?xml version="1.0" encoding="utf-8"?>
<!-- This file was generated by Bakefile (http://bakefile.org). Do not modify, all changes will be overwritten! -->
"""

class XmlFormatter(object):
    """
    Formats Node hierarchy into XML output that looks like Visual Studio's native format.
    """

    def __init__(self, paths_info):
        self.expr_formatter = VS2010ExprFormatter(paths_info)

    def format(self, node):
        return XML_HEADER + self._format_node(node, "")

    def _format_node(self, n, indent):
        s = "%s<%s" % (indent, n.name)
        for key, value in n.attrs.iteritems():
            s += ' %s=%s' % (key, quoteattr(self._format_value(value)))
        if n.children:
            s += ">\n"
            subindent = indent + "  "
            for key, value in n.children:
                if isinstance(value, Node):
                    assert key == value.name
                    s += self._format_node(value, subindent)
                else:
                    v = escape(self._format_value(value))
                    if v:
                        s += "%s<%s>%s</%s>\n" % (subindent, key, v, key)
                    # else: empty value, don't write that

            s += "%s</%s>\n" % (indent, n.name)
        else:
            s += " />\n"
        return s

    def _format_value(self, val):
        if isinstance(val, bkl.expr.Expr):
            s = self.expr_formatter.format(val)
        elif isinstance(val, types.BooleanType):
            s = "true" if val else "false"
        elif isinstance(val, types.ListType):
            s = ";".join(self._format_value(x) for x in val)
        else:
            s = str(val)
        return s


class VS2010Solution(OutputFile):
    def __init__(self, module):
        slnfile = module["vs2010.solutionfile"].as_native_path_for_output(module)
        super(VS2010Solution, self).__init__(slnfile, EOL_WINDOWS)
        self.name = module.name
        self.write(codecs.BOM_UTF8)
        self.write("\n")
        self.write("Microsoft Visual Studio Solution File, Format Version 11.00\n")
        self.write("# Visual Studio 2010\n")
        self.projects = []
        self.subsolutions = []
        paths_info = bkl.expr.PathAnchorsInfo(
                                    dirsep="\\",
                                    outfile=slnfile,
                                    builddir=os.path.dirname(slnfile), # unused
                                    model=module)
        self.formatter = VS2010ExprFormatter(paths_info)

    def add_project(self, name, guid, projectfile):
        self.projects.append((name, guid, projectfile))

    def add_subsolution(self, solution):
        self.subsolutions.append(solution)

    def all_projects(self):
        for p in self.projects:
            yield p
        for sln in self.subsolutions:
            for p in sln.all_projects():
                yield p

    def commit(self):
        guids = []
        for name, guid, filename in self.all_projects():
            guids.append(guid)
            p = ('Project("8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942") = "%s", "%s", "%s"\nEndProject\n' %
                 (name, self.formatter.format(filename), guid))
            self.write(str(p))

        self.write("Global\n")
        self.write("\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n")
        self.write("\t\tDebug|Win32 = Debug|Win32\n")
        self.write("\t\tRelease|Win32 = Release|Win32\n")
        self.write("\tEndGlobalSection\n")
        self.write("\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n")
        for guid in guids:
            self.write("\t\t%s.Debug|Win32.ActiveCfg = Debug|Win32\n" % guid)
            self.write("\t\t%s.Debug|Win32.Build.0 = Debug|Win32\n" % guid)
            self.write("\t\t%s.Release|Win32.ActiveCfg = Release|Win32\n" % guid)
            self.write("\t\t%s.Release|Win32.Build.0 = Release|Win32\n" % guid)
        self.write("\tEndGlobalSection\n")
        self.write("EndGlobal\n")
        super(VS2010Solution, self).commit()


# TODO: Both of these should be done as an expression once proper functions
#       are implemented, as $(dirname(vs2010.solutionfile)/$(id).vcxproj)
def _default_solution_name(module):
    """same directory and name as the module's bakefile, with ``.sln`` extension"""
    return bkl.expr.PathExpr([bkl.expr.LiteralExpr(module.name + ".sln")])

def _project_name_from_solution(target):
    """``$(id).vcxproj`` in the same directory as the ``.sln`` file"""
    sln = target["vs2010.solutionfile"]
    return bkl.expr.PathExpr(sln.components[:-1] + [bkl.expr.LiteralExpr("%s.vcxproj" % target.name)], sln.anchor)


class VS2010Toolset(Toolset):
    """
    Visual Studio 2010.
    """

    name = "vs2010"

    exename_extension = "exe"
    libname_extension = "lib"

    properties_target = [
        Property("vs2010.projectfile",
                 type=PathType(),
                 default=_project_name_from_solution,
                 inheritable=False,
                 doc="File name of the project for the target."),
        ]

    properties_module = [
        Property("vs2010.solutionfile",
                 type=PathType(),
                 default=_default_solution_name,
                 inheritable=False,
                 doc="File name of the solution file for the module."),
        ]

    def generate(self, project):
        # generate vcxproj files and prepare solutions
        for m in project.modules:
            self.gen_for_module(m)
        # Commit solutions; this must be done after processing all modules
        # because of inter-module dependencies and references.
        for m in project.modules:
            for sub in m.submodules:
                m.solution.add_subsolution(sub.solution)
        for m in project.modules:
            m.solution.commit()


    def gen_for_module(self, module):
        # attach VS2010-specific data to the model
        module.solution = VS2010Solution(module)

        for t in module.targets.itervalues():
            try:
                self.gen_for_target(t)
            except bkl.error.Error as e:
                if e.pos is None:
                    e.pos = t.source_pos
                raise


    def gen_for_target(self, target):
        sln = target.parent.solution

        projectfile = target["vs2010.projectfile"]
        filename = projectfile.as_native_path_for_output(target)

        paths_info = bkl.expr.PathAnchorsInfo(
                                    dirsep="\\",
                                    outfile=filename,
                                    # FIXME: this needs to be config-specific
                                    builddir=os.path.dirname(filename),
                                    model=target)

        is_library = (target.type.name == "library")
        is_exe = (target.type.name == "exe")

        root = Node("Project")
        root["DefaultTargets"] = "Build"
        root["ToolsVersion"] = "4.0"
        root["xmlns"] = "http://schemas.microsoft.com/developer/msbuild/2003"

        guid = GUID(NAMESPACE_PRJ, sln.name, target.name)
        configs = ["Debug", "Release"]

        n_configs = Node("ItemGroup", Label="ProjectConfigurations")
        for c in configs:
            n = Node("ProjectConfiguration", Include="%s|Win32" % c)
            n.add("Configuration", c)
            n.add("Platform", "Win32")
            n_configs.add(n)
        root.add(n_configs)

        n_globals = Node("PropertyGroup", Label="Globals")
        n_globals.add("ProjectGuid", guid)
        n_globals.add("Keyword", "Win32Proj")
        n_globals.add("RootNamespace", target.name)
        root.add(n_globals)

        root.add("Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props")

        for c in configs:
            n = Node("PropertyGroup", Label="Configuration")
            n["Condition"] = "'$(Configuration)|$(Platform)'=='%s|Win32'" % c
            if is_exe:
                n.add("ConfigurationType", "Application")
            elif is_library:
                n.add("ConfigurationType", "StaticLibrary")
            else:
                assert False, "unknown target type %s" % target.type.name
            n.add("UseDebugLibraries", c == "Debug")
            if target["win32-unicode"].as_py():
                n.add("CharacterSet", "Unicode")
            else:
                n.add("CharacterSet", "MultiByte")
            root.add(n)

        root.add("Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.props")
        root.add("ImportGroup", Label="ExtensionSettings")

        for c in configs:
            n = Node("ImportGroup", Label="PropertySheets")
            n["Condition"] = "'$(Configuration)|$(Platform)'=='%s|Win32'" % c
            n.add("Import",
                  Project="$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props",
                  Condition="exists('$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props')",
                  Label="LocalAppDataPlatform")
            root.add(n)

        root.add("PropertyGroup", Label="UserMacros")

        for c in configs:
            n = Node("PropertyGroup")
            if not is_library:
                n.add("LinkIncremental", c == "Debug")
            # TODO: add TargetName only if it's non-default
            n.add("TargetName", target[target.type.basename_prop])
            if n.has_children():
                n["Condition"] = "'$(Configuration)|$(Platform)'=='%s|Win32'" % c
            root.add(n)

        for c in configs:
            n = Node("ItemDefinitionGroup")
            n["Condition"] = "'$(Configuration)|$(Platform)'=='%s|Win32'" % c
            n_cl = Node("ClCompile")
            n_cl.add("WarningLevel", "Level3")
            if c == "Debug":
                n_cl.add("Optimization", "Disabled")
                std_defs = "WIN32;_DEBUG"
            else:
                n_cl.add("Optimization", "MaxSpeed")
                n_cl.add("FunctionLevelLinking", True)
                n_cl.add("IntrinsicFunctions", True)
                std_defs = "WIN32;NDEBUG"
            if is_exe:
                std_defs += ";_CONSOLE"
            if is_library:
                std_defs += ";_LIB"
            std_defs += ";%(PreprocessorDefinitions)"
            defs = bkl.expr.ListExpr(
                            target["defines"].items +
                            [bkl.expr.LiteralExpr(std_defs)])
            n_cl.add("PreprocessorDefinitions", defs)
            n_cl.add("AdditionalIncludeDirectories", target["includedirs"])
            # Currently we don't make any distinction between preprocessor, C
            # and C++ flags as they're basically all the same at MSVS level
            # too and all go into the same place in the IDE and same
            # AdditionalOptions node in the project file.
            all_cflags = target["cppflags"].as_py() + target["cflags"].as_py() + target["cxxflags"].as_py()
            if all_cflags:
                n_cl.add("AdditionalOptions", "%s %%(AdditionalOptions)" % " ".join(all_cflags))
            n.add(n_cl)
            n_link = Node("Link")
            n_link.add("SubSystem", "Console" if is_exe else "Windows")
            n_link.add("GenerateDebugInformation", True)
            if c == "Release":
                n_link.add("EnableCOMDATFolding", True)
                n_link.add("OptimizeReferences", True)
            if is_exe:
                ldflags = target["ldflags"].as_py()
                if ldflags:
                    n_link.add("AdditionalOptions", "%s %%(AdditionalOptions)" % " ".join(ldflags))
            n.add(n_link)
            root.add(n)

        # Source files:
        items = Node("ItemGroup")
        root.add(items)
        for sfile in target.sources:
            ext = sfile.filename.get_extension()
            # FIXME: make this more solid
            if ext in ['cpp', 'c']:
                items.add("ClCompile", Include=sfile.filename)
            else:
                # FIXME: handle both compilation into cpp and c files
                genfiletype = bkl.compilers.CxxFileType.get()
                genname = sfile.filename.change_extension("cpp")
                # FIXME: needs to flatten the path too
                genname.anchor = bkl.expr.ANCHOR_BUILDDIR
                ft_from = bkl.compilers.get_file_type(ext)
                compiler = bkl.compilers.get_compiler(self, ft_from, genfiletype)

                customBuild = Node("CustomBuild", Include=sfile.filename)
                customBuild.add("Command", compiler.commands(self, target, sfile.filename, genname))
                customBuild.add("Outputs", genname)
                items.add(customBuild)
                items.add("ClCompile", Include=genname)

        # Headers files:
        if target.headers:
            items = Node("ItemGroup")
            root.add(items)
            for sfile in target.headers:
                items.add("ClInclude", Include=sfile.filename)

        root.add("Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.targets")
        root.add("ImportGroup", Label="ExtensionTargets")

        f = OutputFile(filename, EOL_WINDOWS)
        f.write(XmlFormatter(paths_info).format(root))
        f.commit()
        sln.add_project(target.name, guid, projectfile)

        self._write_filters_file_for(filename)


    def _write_filters_file_for(self, filename):
        f = OutputFile(filename + ".filters", EOL_WINDOWS)
        f.write("""\
<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <Filter Include="Source Files">
      <UniqueIdentifier>{4FC737F1-C7A5-4376-A066-2A32D752A2FF}</UniqueIdentifier>
      <Extensions>cpp;c;cc;cxx;def;odl;idl;hpj;bat;asm;asmx</Extensions>
    </Filter>
    <Filter Include="Header Files">
      <UniqueIdentifier>{93995380-89BD-4b04-88EB-625FBE52EBFB}</UniqueIdentifier>
      <Extensions>h;hpp;hxx;hm;inl;inc;xsd</Extensions>
    </Filter>
    <Filter Include="Resource Files">
      <UniqueIdentifier>{67DA6AB6-F800-4c08-8B7A-83BB121AAD01}</UniqueIdentifier>
      <Extensions>rc;ico;cur;bmp;dlg;rc2;rct;bin;rgs;gif;jpg;jpeg;jpe;resx;tiff;tif;png;wav;mfcribbon-ms</Extensions>
    </Filter>
  </ItemGroup>
</Project>
""")
        f.commit()


