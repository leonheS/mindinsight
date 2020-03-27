# Copyright 2019 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Start mindinsight service."""

import os
import argparse
from importlib import import_module

import psutil

from mindinsight.conf import settings
from mindinsight.utils.command import BaseCommand
from mindinsight.utils.hook import HookUtils
from mindinsight.utils.hook import init
from mindinsight.utils.exceptions import PortNotAvailableError


class ConfigAction(argparse.Action):
    """Config action class definition."""

    def __call__(self, parser, namespace, values, option_string=None):
        """
        Inherited __call__ method from argparse.Action.

        Args:
            parser (ArgumentParser): Passed-in argument parser.
            namespace (Namespace): Namespace object to hold arguments.
            values (object): Argument values with type depending on argument definition.
            option_string (str): Optional string for specific argument name. Default: None.
        """
        config = values
        if not config:
            setattr(namespace, self.dest, config)

        # python:full.path.for.config.module
        if config.startswith('python:'):
            config = config[len('python:'):]
            try:
                import_module(config)
            except ModuleNotFoundError:
                parser.error(f'{option_string} {config} not exists')

            config = f'python:{config}'
        else:
            # file:/full/path/for/config/module.py
            if config.startswith('file:'):
                config = config[len('file:'):]

            if config.startswith('~'):
                config = os.path.realpath(os.path.expanduser(config))

            if not config.startswith('/'):
                config = os.path.realpath(os.path.join(os.getcwd(), config))

            if not os.path.exists(config):
                parser.error(f'{option_string} {config} not exists')

            if not os.access(config, os.R_OK):
                parser.error(f'{option_string} {config} not accessible')

            config = f'file:{config}'

        setattr(namespace, self.dest, config)


class WorkspaceAction(argparse.Action):
    """Workspace action class definition."""

    def __call__(self, parser, namespace, values, option_string=None):
        """
        Inherited __call__ method from argparse.Action.

        Args:
            parser (ArgumentParser): Passed-in argument parser.
            namespace (Namespace): Namespace object to hold arguments.
            values (object): Argument values with type depending on argument definition.
            option_string (str): Optional string for specific argument name. Default: None.
        """
        workspace = os.path.realpath(values)
        setattr(namespace, self.dest, workspace)


class PortAction(argparse.Action):
    """Port action class definition."""

    MIN_PORT = 1
    MAX_PORT = 65535

    OPEN_PORT_LIMIT = 1024

    def __call__(self, parser, namespace, values, option_string=None):
        """
        Inherited __call__ method from argparse.Action.

        Args:
            parser (ArgumentParser): Passed-in argument parser.
            namespace (Namespace): Namespace object to hold arguments.
            values (object): Argument values with type depending on argument definition.
            option_string (str): Optional string for specific argument name. Default: None.
        """
        port = values
        if not self.MIN_PORT <= port <= self.MAX_PORT:
            parser.error(f'{option_string} should be chosen from {self.MIN_PORT} to {self.MAX_PORT}')

        setattr(namespace, self.dest, port)


class Command(BaseCommand):
    """
    Start mindinsight service.
    """

    name = 'start'
    description = 'startup mindinsight service'

    def add_arguments(self, parser):
        """
        Add arguments to parser.

        Args:
            parser (ArgumentParser): Specify parser to which arguments are added.
        """
        parser.add_argument(
            '--config',
            type=str,
            action=ConfigAction,
            help="""
                Specify path for user config module or file of the form python:path.to.config.module
                or file:/path/to/config.py
            """)

        parser.add_argument(
            '--workspace',
            type=str,
            action=WorkspaceAction,
            help="""
                Specify path for user workspace. Default is %s.
            """ % settings.WORKSPACE)

        parser.add_argument(
            '--port',
            type=int,
            action=PortAction,
            help="""
                Custom port ranging from %s to %s. Default value is %s.
            """ % (PortAction.MIN_PORT, PortAction.MAX_PORT, settings.PORT))

        for hook in HookUtils.instance().hooks():
            hook.register_startup_arguments(parser)

    def update_settings(self, args):
        """
        Update settings.

        Args:
            args (Namespace): parsed arguments to hold customized parameters.
        """
        kwargs = {}
        for key, value in args.__dict__.items():
            if value is not None:
                kwargs[key] = value

        init(**kwargs)

    def run(self, args):
        """
        Execute for start command.

        Args:
            args (Namespace): Parsed arguments to hold customized parameters.
        """
        for key, value in args.__dict__.items():
            if value is not None:
                self.logger.info('%s = %s', key, value)

        try:
            self.check_port()
        except PortNotAvailableError as error:
            print(error.message)
            self.logger.error(error.message)
            return

        run_module = import_module('mindinsight.backend.run')
        run_module.start()

        self.logger.info('Start mindinsight done.')

    def check_port(self):
        """Check port."""
        if os.getuid() != 0 and settings.PORT < PortAction.OPEN_PORT_LIMIT:
            raise PortNotAvailableError(
                f'Port {settings.PORT} below {PortAction.OPEN_PORT_LIMIT} is not allowed by current user.')

        connections = psutil.net_connections()
        for connection in connections:
            if connection.status != 'LISTEN':
                continue
            if connection.laddr.port == settings.PORT:
                raise PortNotAvailableError(f'Port {settings.PORT} is not available for MindInsight')
