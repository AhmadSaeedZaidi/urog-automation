FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 user
USER user

# Install Python dependencies
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=user:user . .

# Install local editable packages
RUN pip install --no-cache-dir \
    -e libs/dao \
    -e libs/ingest \
    -e libs/generator \
    -e libs/forms

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
