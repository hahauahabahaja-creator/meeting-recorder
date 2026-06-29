# Official Python runtime image use karenge (3.11 is stable)
FROM python:3.11-slim

# System dependencies jo Playwright (Chromium) ke liye zaroori hain
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libgbm1 \
    libasound2 \
    libxcomposite1 \
    libxdamage1 \
    libxkbcommon0 \
    libxrandr2 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# Work directory set karenge
WORKDIR /app

# Requirements copy aur install karenge
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser (Chromium) download karenge
RUN playwright install chromium

# Baki saara code copy karenge
COPY . .

# Bot run karne ki command
CMD ["python", "meet_bot.py"]
