# -*- coding: utf-8 -*-
'''
Demonstrates subclassing the Process class.

Try out this example:
    1. Open two terminals in the tcbon project directory
    2. Run `python examples/advanced.py` to start Advanced.
    3. Run `python examples/advanced.py` use Advanced's custom routes.
'''
from __future__ import print_function
import logging
import os
import time

import tcbon


class Advanced(tcbon.Process):

    def __init__(self):
        super(Advanced, self).__init__(
            name='advanced',
            address='127.0.0.1:9876',
            app_dir=os.path.abspath('./examples/advanced'),
        )
        self.count_file = self.app_dir + '/count'
        self.count = 0

    def setup_logger(self, log):
        '''Override to add a StreamHandler to the Process' logger.'''

        formatter = logging.Formatter('%(levelname).1s:%(name)s> %(message)s')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.setLevel(logging.INFO)

    def setup_wsgi(self, wsgi):
        '''Add an additional route to the Flask wsgi server'''

        @wsgi.route('/count')
        def count():
            self.log.info('Client requested count.')
            return tcbon.jsonify({'success': True, 'value': self.count})

        @wsgi.route('/increment', methods=['POST'])
        def increment():
            json = tcbon.request.get_json()
            self.count += json.get('value', 1)
            self.log.info('Client incremented count to %s.' % self.count)
            return tcbon.jsonify({'success': True, 'value': self.count})

        @wsgi.route('/decrement', methods=['POST'])
        def decrement():
            json = tcbon.request.get_json()
            self.count -= json.get('value', 1)
            self.log.info('Client decremented count to %s.' % self.count)
            return tcbon.jsonify({'success': True, 'value': self.count})

    def on_start(self):
        '''Load count from disc.'''

        if not os.path.isdir(self.app_dir):
            os.makedirs(self.app_dir)

        if os.path.isfile(self.count_file):
            self.log.info('Loading count from %s.' % self.count_file)
            with open(self.count_file, 'r') as f:
                self.count = int(f.read())

        self.log.info('Count is %s.' % self.count)

    def on_stop(self):
        self.log.info('Persisting count to %s.' % self.count_file)
        with open(self.count_file, 'w') as f:
            f.write(str(self.count))


if __name__ == '__main__':

    # Create an instance of our Process Subclass
    advanced = Advanced()

    try:

        # The `run_forever` method would work here, but, let's run the
        # process manually to expose how `run_forever` works. It's a good
        # idea to use `start` rather than `run_forever` if you're composing
        # a tcbon.Process in a larger application - like a Qt application.
        advanced.start()

        # Wait for KeyboardInterrupt
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                advanced.stop()

    except tcbon.ProcessExists:

        print('Advanced running at %s.' % advanced.address)

        # Get count - all interactions return a dict
        response = advanced.get('count')
        print("advanced.get('count') -> %s" % response)

        # Modify the count
        response = advanced.send('increment')
        print("advanced.send('increment') -> %s" % response)

        response = advanced.send('increment', {'value': 2})
        print("advanced.send('increment', {'value': 2}) -> %s" % response)

        response = advanced.send('decrement', {'value': 1})
        print("advanced.send('decrement', {'value': 1}) -> %s" % response)
