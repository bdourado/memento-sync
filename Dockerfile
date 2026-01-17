FROM python:3.9-slim

WORKDIR /app

# Install system dependencies if needed (none strictly for these python packages, 
# but sometimes build tools are needed. slim usually has enough for wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies directly
RUN pip install --no-cache-dir streamlit piexif Pillow

COPY app.py .

# Expose Streamlit default port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
