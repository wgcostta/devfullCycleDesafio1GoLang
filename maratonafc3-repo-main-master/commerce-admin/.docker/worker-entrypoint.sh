#!/bin/bash

pip install --cache-dir=/home/django/app/.docker/.pip -r requirements.txt
cd /home/django/app
dockerize -wait tcp://app:8000 -timeout 10s celery worker -B -l info -A commerce_admin.celery -s /tmp/celerybeat-schedule
