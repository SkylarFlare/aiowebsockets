from distutils.core import setup
from distutils.core import Extension

fast_mask = Extension(
    'aiowebsockets.fast_mask', sources=['aiowebsockets/fast_mask.c'])

setup(
    name='aiowebsockets',
    version='0.1',
    description='Fast Callback Based WebSocket Handler for AsyncIO',
    author='Skylar Flare',
    url='https://github.com/SkylarFlare/aiowebsockets',
    packages=['aiowebsockets'],
    ext_modules=[fast_mask]
)
