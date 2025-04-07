#!/bin/sh

cd /opt/SecureStamp

. venv/bin/activate
flask db upgrade
flask run -h localhost -p 3010
deactivate
