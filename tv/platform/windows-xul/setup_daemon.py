import os
import sys
import shutil
from distutils.core import setup
from distutils.extension import Extension
import py2exe
from Pyrex.Distutils import build_ext

# The name of this platform.
platform = 'windows-xul'

# Find the top of the source tree and set search path
root = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), '..', '..')
sys.path[0:0] = [
    os.path.join(root, 'portable', 'dl_daemon'),

    # The daemon's "platform" files are in the private directory
    os.path.join(root, 'portable', 'dl_daemon','private'),
    os.path.join(root, 'portable'),
]
root = os.path.normpath(root)

import util

defaultBinaryKitRoot = os.path.join(os.path.dirname(sys.argv[0]), \
				    '..', '..', '..', 'dtv-binary-kit')
BINARY_KIT_ROOT = defaultBinaryKitRoot
BOOST_ROOT = os.path.join(BINARY_KIT_ROOT, 'boost', 'win32')
BOOST_LIB_PATH = os.path.join(BOOST_ROOT, 'lib')
BOOST_LIB = os.path.join(BOOST_LIB_PATH, 'boost_python-vc71-mt-1_33.lib')
BOOST_INCLUDE_PATH = os.path.join(BOOST_ROOT, 'include', 'boost-1_33')
BOOST_RUNTIMES = [
    os.path.join(BOOST_LIB_PATH, 'boost_python-vc71-mt-1_33.dll'),
    ]

ext_modules=[
    Extension("database", [os.path.join(root, 'portable', 'database.pyx')]),
    Extension("fasttypes", 
        sources = [os.path.join(root, 'portable', 'fasttypes.cpp')],
        extra_objects = [BOOST_LIB],
        include_dirs = [BOOST_INCLUDE_PATH]
    )
]

templateVars = util.readSimpleConfigFile(os.path.join(root, 'resources', 'app.config'))

setup(
    console=[{"dest_base":("%s_Downloader"%templateVars['shortAppName']),"script":os.path.join(root, 'portable', 'dl_daemon', 'Democracy_Downloader.py')}],
    ext_modules=ext_modules,
    zipfile=None,
    cmdclass = {
	'build_ext': build_ext,
    }
)
