FROM tiangolo/uwsgi-nginx-flask:python3.10

ADD . /app
RUN pip3 install -r /app/requirements.txt