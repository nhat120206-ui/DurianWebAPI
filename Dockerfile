
FROM python:3.14-slim

WORKDIR /app

# Cài thư viện hệ thống cho PyODBC
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài thư viện Python
COPY requirements.txt .

RUN python -m pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn DurianWebAPI
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
