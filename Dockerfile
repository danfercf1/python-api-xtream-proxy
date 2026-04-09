FROM python:3.12

# Security: Create a non-root user to run the application
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

RUN mkdir xml

# Security: Set ownership to non-root user
RUN chown -R appuser:appgroup /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

# Security: Ensure all files are owned by non-root user
RUN chown -R appuser:appgroup /app

# Security: Switch to non-root user
USER appuser

CMD ["python", "app.py"]
