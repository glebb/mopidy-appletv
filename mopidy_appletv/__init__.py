# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import os

from mopidy import config, ext


__version__ = '0.1.0'

# TODO: If you need to log, use loggers named after the current Python module
logger = logging.getLogger(__name__)


class Extension(ext.Extension):

    dist_name = 'Mopidy-AppleTv'
    ext_name = 'appletv'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        # TODO: Comment in and edit, or remove entirely
        #schema['username'] = config.String()
        #schema['password'] = config.Secret()
        return schema

    def setup(self, registry):
        # You will typically only implement one of the following things
        # in a single extension.

        # TODO: Edit or remove entirely
        from .frontend import AppleTvFrontend
        registry.add('frontend', AppleTvFrontend)