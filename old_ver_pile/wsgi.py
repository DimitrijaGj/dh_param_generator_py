#!/usr/bin/env python3

from dhparam_final import app, init_application

# Initialize background threads and stock
init_application()

# WSGI entry point
application = app

if __name__ == "__main__":
    application.run(host='0.0.0.0', port=5005)