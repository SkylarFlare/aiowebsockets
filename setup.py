import sys
from distutils.core import setup
from distutils.core import Extension


USE_CYTHON = True
ext = ['c', 'pyx'][int(USE_CYTHON)]

"""
extensions
"""
fast_mask = Extension(
    'aiowebsockets.fast_mask', sources=['aiowebsockets/fast_mask.c'])

ext_framing = Extension(
    'aiowebsockets.framing', ['aiowebsockets/framing.' + ext])

extensions = [fast_mask, ext_framing]

if USE_CYTHON:
    from Cython.Build import cythonize
    extensions = cythonize(extensions)


setup(
    name='aiowebsockets',
    version='0.1',
    description='Fast Callback Based WebSocket Handler for AsyncIO',
    author='Skylar Flare',
    url='https://github.com/SkylarFlare/aiowebsockets',
    packages=['aiowebsockets'],
    install_requires=[
        'uvloop'
    ],

    ext_modules=extensions
)
