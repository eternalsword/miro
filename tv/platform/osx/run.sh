#!/bin/bash
# Miro - an RSS based video player application
# Copyright (C) 2005-2010 Participatory Culture Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the OpenSSL
# library.
#
# You must obey the GNU General Public License in all respects for all of
# the code used other than OpenSSL. If you modify file(s) with this
# exception, you may extend this exception to your version of the file(s),
# but you are not obligated to do so. If you do not wish to do so, delete
# this exception statement from your version. If you delete this exception
# statement from all source files in the program, then also delete it here.


OS_VERSION=$(uname -r | cut -d . -f 1)

if [ $OS_VERSION == "8" ]; then
    PYTHON_VERSION=2.4
    PYTHON_ROOT=/Library/Frameworks/Python.framework/Versions/$PYTHON_VERSION
    #export MACOSX_DEPLOYMENT_TARGET=10.4
elif [ $OS_VERSION == "9" ]; then
    # PYTHON_VERSION=2.5
    # PYTHON_ROOT=/System/Library/Frameworks/Python.framework/Versions/$PYTHON_VERSION
    # export MACOSX_DEPLOYMENT_TARGET=10.5

    # OSX 10.5 is now finicky about things and needs to run with a real build.
    # So we kick off brun.sh.
    ./brun.sh
    exit
elif [ $OS_VERSION == "10" ]; then
    PYTHON_VERSION=2.6
    PYTHON_ROOT=/System/Library/Frameworks/Python.framework/Versions/$PYTHON_VERSION
    export MACOSX_DEPLOYMENT_TARGET=10.6
fi

PYTHON=$PYTHON_ROOT/bin/python$PYTHON_VERSION

export VERSIONER_PYTHON_VERSION=$PYTHON_VERSION
export VERSIONER_PYTHON_PREFER_32_BIT=yes

if [ $OS_VERSION == "8" ]; then
    $PYTHON setup.py py2app --dist-dir . -A "$@" && Miro.app/Contents/MacOS/Miro
else
    $PYTHON setup.py py2app --dist-dir . -A "$@" && arch -`arch` Miro.app/Contents/MacOS/Miro
fi