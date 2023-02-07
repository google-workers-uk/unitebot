FROM python:3.9-slim

ADD requirements.txt .
RUN pip install -r requirements.txt

ADD verify.py .
CMD ["python", "./verify.py"]