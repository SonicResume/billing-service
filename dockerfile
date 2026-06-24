FROM python:3.11-slim

WORKDIR /app

# install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy project
COPY . .

# expose port (Render will override with $PORT)
EXPOSE 8000

# start app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
