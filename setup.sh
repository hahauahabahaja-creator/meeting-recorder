#!/bin/bash

# PRODUCTION-GRADE ENVIRONMENT SETUP
echo "🚀 Initializing Production Environment..."

# 1. Update and Install System Dependencies
sudo apt-get update && sudo apt-get install -y \
    xvfb \
    ffmpeg \
    pulseaudio \
    x11vnc \
    novnc \
    websockify \
    python3-pip \
    curl \
    jq

# 2. Install Ngrok if not present
if ! command -v ngrok &> /dev/null
then
    echo "📦 Installing Ngrok..."
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
    sudo apt-get update && sudo apt-get install ngrok
fi

# 3. Setup PulseAudio Virtual Sink (CRITICAL for Zero-Lag Audio)
echo "🔊 Configuring PulseAudio Virtual Sink..."
pulseaudio -D --exit-idle-time=-1 || true
sleep 2
pactl load-module module-null-sink sink_name=Virtual_Sink sink_properties=device.description=Virtual_Sink || true
pactl set-default-sink Virtual_Sink || true
pactl set-default-source Virtual_Sink.monitor || true

# 4. Start Virtual Frame Buffer
echo "🖥️ Initializing Xvfb :99 (1080p)..."
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

echo "✅ Environment Setup Complete."
