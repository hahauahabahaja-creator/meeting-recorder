#!/bin/bash
echo "? Initializing GHOST v3.0 Environment..."
sudo apt-get update && sudo apt-get install -y xvfb ffmpeg pulseaudio x11vnc novnc websockify python3-pip curl jq unzip
pulseaudio -D --exit-idle-time=-1 || true
sleep 2
pactl load-module module-null-sink sink_name=Virtual_Sink || true
pactl set-default-sink Virtual_Sink || true
pactl set-default-source Virtual_Sink.monitor || true
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
echo "? Applying Ghost Theme..."
if [ -d "/usr/share/novnc" ]; then
    sudo sed -i 's/<title>noVNC<\/title>/<title>GHOST v3.0<\/title>/g' /usr/share/novnc/vnc.html
    GHOST_ICON="https://cdn-icons-png.flaticon.com/512/2353/2353687.png"
    sudo curl -L -o /usr/share/novnc/app/images/favicon.ico \$GHOST_ICON
    sudo curl -L -o /usr/share/novnc/app/images/logo.png \$GHOST_ICON
    echo ".noVNC_logo { display: none !important; }" | sudo tee -a /usr/share/novnc/app/styles/base.css
    echo ".noVNC_status_bar:before { content: '? GHOST'; color: white; font-weight: bold; margin-left: 10px; font-size: 1.2em; letter-spacing: 2px; }" | sudo tee -a /usr/share/novnc/app/styles/base.css
fi
echo "?? Downloading Free Transcription Model..."
mkdir -p model
curl -L https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o model.zip
unzip model.zip -d model
mv model/vosk-model-small-en-us-0.15/* model/
rm -rf model.zip
echo "? Setup Complete."
