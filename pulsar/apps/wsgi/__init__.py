'''
Pulsar is shipped with a Http applications which conforms the python
web server gateway interface (WSGI).

The application can be used in conjunction with several web frameworks
as well as the pulsar RPC handler in :mod:`pulsar.apps.rpc`.
'''
import sys
import traceback
import errno
import socket

import pulsar
from pulsar.net import HttpResponse

from .handlers import *


class WSGIApplication(pulsar.Application):
    '''A WSGI application running on pulsar concurrent framework.
It can be configured to run as a multiprocess or a multithreaded server.'''
    app = 'wsgi'
    
    def on_config(self):
        if not pulsar.platform.multiProcessSocket():
            self.cfg.set('concurrency','thread')
    
    def get_task_queue(self): 
        if self.cfg.concurrency == 'process':
            return None
        else:
            return pulsar.ThreadQueue()
        
    def update_worker_paramaters(self, monitor, params):
        '''If running as a multiprocess, pass the socket to the worker
parameters.'''
        #TODO RAISE ERROR IN WINDOWS WHEN USING PYTHON 2
        if not monitor.task_queue:
            params['socket'] = monitor.socket
        return params
        
    def worker_start(self, worker):
        # If the worker is a process and it is listening to a socket
        # Add the socket handler to the event loop, otherwise do nothing.
        # The worker will receive requests on a task queue
        if worker.socket:
            worker.socket.setblocking(False)
            handler = HttpHandler(worker)
            worker.ioloop.add_handler(worker.socket,
                                      handler,
                                      worker.ioloop.READ)
        
    def handle_request(self, worker, request):
        environ = request.wsgi_environ()
        if not environ:
            yield request.on_headers
            environ = request.wsgi_environ()
        cfg = worker.cfg
        mt = cfg.concurrency == 'thread' and cfg.workers > 1
        mp = cfg.concurrency == 'process' and cfg.workers > 1
        environ.update({"pulsar.worker": worker,
                        "wsgi.multithread": mt,
                        "wsgi.multiprocess": mp})
        # Create the response object
        response = HttpResponse(request)
        response.foce_close()
        data = worker.app_handler(environ, response.start_response)
        yield response.write(data)
        #yield response.close()
        yield response
            
    def monitor_start(self, monitor):
        '''If the concurrency model is thread, a new handler is
added to the monitor event loop which listen for requests on
the socket.'''
        # We have a task queue, This means the monitor itself listen for
        # requests on the socket and delegate the handling to the
        # workers
        address = self.cfg.address
        if address:
            socket = pulsar.create_socket(address, log = monitor.log)
        else:
            raise pulsar.ImproperlyConfigured('\
 WSGI application with no address for socket')
        
        if monitor.task_queue is not None:
            monitor.set_socket(socket)
            monitor.ioloop.add_handler(monitor.socket,
                                       HttpPoolHandler(monitor),
                                       monitor.ioloop.READ)
        else:
            monitor.socket = socket
            
            
    def monitor_stop(self, monitor):
        if monitor.task_queue is not None:
            monitor.ioloop.remove_handler(monitor.socket)


def createServer(callable = None, **params):
    return WSGIApplication(callable = callable, **params)
    
