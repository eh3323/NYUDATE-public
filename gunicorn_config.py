# Gunicorn configuration for production
import os
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Preload app for better performance, but handle database connections carefully
preload_app = False  # Set to False to avoid database connection issues

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

def post_fork(server, worker):
    """Called after worker processes are forked"""
    # Reset database connections in each worker process
    try:
        from app import app, db, init_db_connection
        
        # Use app context for database operations
        with app.app_context():
            # Call our initialization function which handles connection reset
            init_db_connection()
            server.log.info(f"Worker {worker.pid}: Database connections initialized after fork")
            
    except Exception as e:
        server.log.error(f"Worker {worker.pid}: Error initializing database connections: {e}")

def pre_fork(server, worker):
    """Called before worker processes are forked"""
    server.log.info(f"About to fork worker {worker}")

def worker_exit(server, worker):
    """Called when worker is about to exit"""
    server.log.info(f"Worker {worker.pid} exiting...")

def worker_int(worker):
    """Called when worker receives INT or QUIT signal"""
    worker.log.info(f"Worker {worker.pid} received signal, cleaning up...")

def pre_exec(server):
    """Called before starting workers"""
    server.log.info("Server starting up...")

def when_ready(server):
    """Called when server is ready to serve requests"""
    server.log.info("Server ready to handle requests")