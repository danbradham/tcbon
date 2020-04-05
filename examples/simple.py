# -*- coding: utf-8 -*-
'''
Demonstrates a very simple Process with an event handler for 'ack' events.

Try out this example:
    1. Open two terminals in the tcbon project directory
    2. Run `python examples/simple.py` to start the simple Process.
    3. Run `python examples/simple.py` to send an event named 'ack' and
       receive a response from the on_ack event handler.
'''
from __future__ import print_function
import tcbon


def on_ack(event):
    return {'message': 'Hello there!'}


# Create a Process
simple = tcbon.Process('simple')
simple.register_event_handler('ack', on_ack)


if __name__ == '__main__':

    try:
        simple.run_forever()
    except tcbon.ProcessExists:
        # Process already running, send an event instead
        response = simple.send('event', {'name': 'Null'})
        print(response)
