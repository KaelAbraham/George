FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . /app

EXPOSE 6001

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:6001", "app:app"]
