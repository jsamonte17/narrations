# Gamitin ang opisyal na Python image sa Debian/Ubuntu base
FROM python:3.10-slim

# Mag-set ng working directory sa loob ng container
WORKDIR /app

# Mag-install ng system dependencies (kabilang ang FFmpeg para sa audio/video processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# I-upgrade ang pip at i-install ang edge-tts at iba pang kinakailangang Python libraries
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir edge-tts asyncio

# Kopyahin ang iyong mga script o txt files sa container (opsyonal kung gagamitin mo ang current folder)
COPY . /app

# Default command kapag binuksan ang container
CMD ["bash"]