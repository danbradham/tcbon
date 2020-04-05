tcbon
-----
There can be only one!

A library with one class, `Process`, designed to help you keep a single
instance of your python application alive. This is useful if you've written
a UI application and you don't want people to launch multiple instances of
it.

tcbon accomplishes this by running a small Flask wsgi server in a background
thread, and writing the pid and the server's address to a file. The file
containing the pid and address allows the application to check for the
existance of a running instance prior to starting. An added benefit to this
technique is that the `Process` class can act as a way for external
applications to communicate with your application by sending post requests.


How does it look?

.. code-block::

    import tcbon

    my_app = tcbon.Process('my_app', debug=True)

    try:
        my_app.run_forever()
    except tcbon.ProcessExists:
        print('my_app already running.')


Check out the examples to see more detailed usage. Including subclassing,
sending events, and registering event handlers.


API
---

::

class Process()
    Allows only one instance of an application to run at a time.

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

    def run_forever(self)
        Convenient method to run this Process forever. Gracefully exits
        on KeyboardInterrupt.

    def start(self)
        Start the Process including background wsgi_thread.

    def stop(self)
        Stop the server by sending a shutdown event.

    def get(self, route='/')
        Sends a get request to the Process' wsgi server.

    def send(self, route, payload=None)
        Sends a post request with a json payload to the specified route.

        Examples:
            >>> import tcbon
            >>> p = tcbon.Process('test')
            >>> p.send('event', {'name': 'ack'})

    def setup_logger(self, log)
        Subclasses can override this method to add handlers to this
        Applications logger.

    def setup_wsgi(self, wsgi)
        Subclasses can override this method to prepare the Flask
        wsgi server.

    def on_start(self)
        Subclasses can override this method to add additional behavior
        on start. This is run prior to starting the wsgi server.

    def on_stop(self)
        Subclasses can override this method to perform teardown for the
        application. This is run prior to sending a shutdown event.

    def register_event_handler(self, event, handler)
        Specify the handler for an event.

    def unregister_event_handler(self, event)
        Remove a handler from an event.
