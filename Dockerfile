FROM python:2.7.13

RUN pip install lxml requests

COPY xunitbucket.py /usr/local/bin/xunitbucket
