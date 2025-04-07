#!/bin/sh

cd /opt/SecureStamp

. venv/bin/activate
date > log.txt
python update_files.py 2>&1 >> log.txt
date >> log.txt
deactivate
