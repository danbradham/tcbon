# -*- coding: utf-8 -*-
'''
tcbon
-----
There can be only one!

A utility to help you keep only one instance of your application alive at a
time.
'''
from __future__ import print_function

# Standard library imports
import atexit
import logging
import os
import traceback
import signal
import socket
import subprocess
import sys
import time
import threading
from functools import partial

# Third party imports
import requests
from appdirs import user_data_dir
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException


def get_open_port():
    '''Get an available port to use.'''

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    return sock.getsockname()[1]


class Error(Exception):
    '''Base class for all tcbon exceptions.'''


class ProcessExists(Error):
    '''Raised when you try to start a Process that is already running.'''


class ProcessDoesNotExist(Error):
    '''Raised when you try to interact with a Process that has not been
    started. This includes, stop, get, and send methods.'''


class Process(object):
    '''Allows only one instance of an application to run at a time.

    When started each Process runs a small flask server on an available port
    or the http address of your choice. Then the pid and address are written
    to a file. When another Process with the same name is created, this file
    can be used to check if a Process is already running and send events to
    the Process if it is running. Events are simple dictionaries that have at
    least one key "name".

    Attributes:
        log (logging.Logger): The Process object's logger
        wsgi (flask.Flask): Flask application object
        wsgi_thread (threading.Thread): The Thread containg the Flask app
        wsgi_running (bool): True when the wsgi_thread is running
        event_handlers (dict): Contains all event handlers

    Properties:
        pid_file (str): Full path to Process' pid file
        running (bool): True when Process is running

    Arguments:
        name (str): Name of the application
        address (str): Optional address like '127.0.0.1:9876
        app_dir (str): Optional directory in which to store .pid file
        debug (bool): Set logging level to DEBUG
    '''

    def __init__(self, name, address=None, app_dir=None, debug=False):
        self.name = name
        app_dir = (app_dir or user_data_dir(appname=name))
        self.app_dir = app_dir.replace('\\', '/').rstrip('/')
        self.pid = None
        if address:
            self.address = 'http://' + address.replace('http://', '')
        else:
            self.address = None
        self.debug = debug
        self.log = self._logger(name, debug)
        self.wsgi = self._wsgi(name)
        self.wsgi_thread = None
        self.wsgi_running = False
        self.event_handlers = {}

    def __str__(self):
        return '<%s>("%s")' % (self.__class__.__name__, self.name)

    def __repr__(self):
        return '<%s>(name="%s", address="%s", app_dir="%s")' % (
            self.__class__.__name__,
            self.name,
            self.address,
            self.app_dir
        )

    def _logger(self, name, debug):
        # Silence werkzeug
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        os.environ['WERKZEUG_RUN_MAIN'] = 'true'

        # Internal Logger
        log = logging.getLogger(name)
        log.addHandler(logging.NullHandler())

        # Add a streamhandler in debug mode
        if debug:
            formatter = logging.Formatter(
                '%(levelname).1s:%(name)s> %(message)s'
            )
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            log.addHandler(handler)
            log.setLevel(logging.DEBUG)

        self.setup_logger(log)
        return log

    def _wsgi(self, name):
        '''Creates a Flask Application object with default routes.'''

        wsgi = Flask(name)

        @wsgi.route('/')
        def index():
            return jsonify({
                'succes': True,
                'name': self.name,
                'pid': str(os.getpid()),
                'app_dir': self.app_dir,
                'address': self.address,
            })

        @wsgi.route('/event', methods=['POST'])
        def receive_event():
            event = request.get_json()
            if 'name' not in event:
                return jsonify({
                    'success': False,
                    'message': 'Event missing required field "name".',
                })

            response = self._handle_event(event)
            return jsonify(response)

        @wsgi.route('/stop', methods=['POST'])
        def stop():
            server_shutdown = request.environ['werkzeug.server.shutdown']
            server_shutdown()
            return jsonify({
                'success': True,
                'message': 'Shutting down...',
            })

        @wsgi.route('/restart', methods=['POST'])
        def restart():
            # TODO: This is only partially functioning from a windows terminal
            self.log.info('Restarting %s' % repr(self))
            server_shutdown = request.environ['werkzeug.server.shutdown']

            def do_restart(server_shutdown):
                os.execl(sys.executable, sys.executable, *sys.argv)

            thread = threading.Thread(
                target=do_restart,
                args=(server_shutdown,)
            )
            thread.start()

            server_shutdown()
            return jsonify({
                'success': True,
                'message': 'Restarting...',
            })

        @wsgi.errorhandler(HTTPException)
        def handle_error(e):
            self.log.error(str(e))
            response = jsonify({'success': False, 'message': str(e)})
            response.status_code = e.status_code
            return response

        self.setup_wsgi(wsgi)
        return wsgi

    def _handle_event(self, event):
        '''Handle one event. Dispatches events to registered handlers.'''
        handler = self.event_handlers.get(event['name'], None)
        if handler:
            try:
                payload = handler(event)
                return dict(
                    success=True,
                    **payload
                )
            except Exception:
                self.log.exception('Event handler raise an exception...')
                exc = traceback.format_exc()
                return {
                    'success': False,
                    'message': exc,
                }

        return {
            'success': True,
            'message': 'Event received. no handler found for ' + event['name'],
        }

    def _read_pid_file(self):
        '''Read the proc's pid file.'''

        self.log.debug('Reading ' + self.pid_file)
        with open(self.pid_file, 'r') as f:
            pid, address = f.readlines()

        return pid, address

    def _write_pid_file(self, pid, address):
        '''Write a proc's pid and address to a pid file.'''

        if not os.path.exists(self.app_dir):
            self.log.debug('Creating ' + self.app_dir)
            os.makedirs(self.app_dir)

        self.log.debug('Writing ' + self.pid_file)
        with open(self.pid_file, 'w') as f:
            f.write(str(pid) + '\n' + self.address)

    @property
    def pid_file(self):
        return self.app_dir + '/.pid'

    @property
    def running(self):
        '''Check if a Process is running.'''

        if self.wsgi_running:
            return True

        if self.address:
            try:
                response = requests.get(self.address)
                json = response.json()
                self.name = json['name']
                self.pid = json['pid']
                self.address = json['address']
                self.app_dir = json['app_dir']
                return True
            except requests.ConnectionError:
                self.log.debug('Process had incorrect address.')

        if not os.path.exists(self.pid_file):
            self.log.debug('Process is not running. No .pid file found.')
            return False

        self.log.debug('Found .pid file')
        try:
            pid, address = self._read_pid_file()
            self.pid = pid
            self.address = address
        except Exception:
            self.log.exception('Invalid .pid file.')
            return False

        # Check the pid first
        if sys.platform == 'win32':
            p = subprocess.Popen(
                'powershell Get-Process -Id ' + str(pid),
                shell=True,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
            if p.wait() == 1:
                self.log.debug('Process %s not found.' % pid)
                return False
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                self.log.debug('Process %s not found.' % pid)
                return False

        self.log.debug('Found Process ' + pid)
        self.log.debug('Checking ' + address)

        # Now check that the flask app is alive
        response = requests.get(address)
        if not response:
            self.log.debug('Got no response from wsgi server.')
            return False

        self.log.debug('WSGI server is running, Process is accepting events.')
        return True

    def run_forever(self):
        '''Convenient method to run this Process forever. Gracefully exits
        on KeyboardInterrupt.

        Use this when Process is your main application object. Otherwise
        use start and manage the shutdown of Process on your own. For example,
        call Process.stop in a Qt Window's closeEvent.
        '''

        self.start()

        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def start(self):
        '''Start the background server and write a pid file.'''

        if self.running:
            raise ProcessExists('%s is already running.' % self.name)

        # Get this Appes attributes
        self.pid = os.getpid()
        if not self.address:
            port = get_open_port()
            self.address = 'http://127.0.0.1:' + str(port)
        else:
            port = self.address.split(':')[-1]

        # Run on_start
        self.on_start()

        # Start wsgi server
        self.wsgi_thread = threading.Thread(
            target=self.wsgi.run,
            kwargs={
                'debug': False,
                'host': '127.0.0.1',
                'port': port,
                'use_reloader': False,
            }
        )
        self.wsgi_thread.start()
        self.wsgi_running = True
        self.log.info('Serving Process %s at %s' % (self.pid, self.address))

        # Stop wsgi server on sigint
        sigterm_handler = signal.getsignal(signal.SIGTERM)
        sigint_handler = signal.getsignal(signal.SIGINT)

        def on_signal(old_handler, signum, frame):
            self.stop()
            if old_handler:
                old_handler()

        signal.signal(signal.SIGTERM, partial(on_signal, sigterm_handler))
        signal.signal(signal.SIGINT, partial(on_signal, sigint_handler))

        # Stop wsgi server on exit
        atexit.register(self.stop)

        # Write pid file with address
        self._write_pid_file(self.pid, self.address)

    def stop(self):
        '''Stop the server by sending a shutdown event.'''

        if not self.running:
            raise ProcessDoesNotExist('Can not find process.')

        # Perform some teardown if we are the wsgi server
        if self.wsgi_running:
            self.on_stop()

        try:
            response = self.send('stop')
        except requests.ConnectionError:
            self.log.error('Process wsgi server already shutdown.')

        if self.wsgi_thread:
            self.log.debug('Waiting for wsgi_thread to finish...')
            self.wsgi_thread.join()

        self.log.debug('WSGI server successfully shut down.')
        self.wsgi_running = False
        self.wsgi_thread = None
        self.wsgi = self._wsgi(self.name)
        return response

    def get(self, route='/'):
        '''Sends a get request to the Process' wsgi server.'''

        if not self.running:
            raise ProcessDoesNotExist('Can not find process.')

        uri = self.address + '/' + route.lstrip('/')
        response = requests.get(uri)
        return response.json()

    def send(self, route, payload=None):
        '''Sends a post request with a json payload to the specified route.

        Examples:
            >>> import tcbon
            >>> p = tcbon.Process('test')
            >>> p.send('event', {'name': 'ack'})
        '''

        if not self.running:
            raise ProcessDoesNotExist('Can not find process.')

        uri = self.address + '/' + route.lstrip('/')
        response = requests.post(uri, json=payload or {})
        return response.json()

    def setup_logger(self, log):
        '''Subclasses can override this method to add handlers to this
        Applications logger.'''

    def setup_wsgi(self, wsgi):
        '''Subclasses can override this method to prepare the Flask
        wsgi server.'''

    def on_start(self):
        '''Subclasses can override this method to add additional behavior
        on start. This is run prior to starting the wsgi server.'''

    def on_stop(self):
        '''Subclasses can override this method to perform teardown for the
        application. This is run prior to sending a shutdown event.'''

    def register_event_handler(self, event, handler):
        '''Specify the handler for an event.'''

        self.log.debug('%s will handle all %s events' % (handler, event))
        self.event_handlers[event] = handler

    def unregister_event_handler(self, event):
        '''Remove a handler from an event.'''

        self.log.debug('Removing handlers for %s' % event)
        self.event_handlers.pop(event, None)
