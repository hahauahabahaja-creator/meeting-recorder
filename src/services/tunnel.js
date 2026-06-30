const { spawn, execSync } = require('child_process');
const axios = require('axios');
const logger = require('../utils/logger');

class TunnelService {
  constructor() {
    this.ngrokProcess = null;
    this.websockifyProcess = null;
    this.vncProcess = null;
  }

  async startUIStream(vncPassword) {
    logger.system('Starting Hybrid UI Stream (VNC + noVNC + Ngrok)...');

    try {
      // 1. Start x11vnc
      this.vncProcess = spawn('x11vnc', [
        '-display', ':99', '-forever', '-shared', '-passwd', vncPassword,
        '-rfbport', '5900', '-listen', '0.0.0.0', '-bg'
      ]);

      // 2. Start websockify (noVNC bridge)
      this.websockifyProcess = spawn('websockify', [
        '--web', '/usr/share/novnc', '6080', 'localhost:5900'
      ]);

      // 3. Start Ngrok
      const ngrokToken = process.env.NGROK_AUTH_TOKEN;
      if (ngrokToken) {
        execSync(`ngrok config add-authtoken ${ngrokToken}`);
        this.ngrokProcess = spawn('ngrok', ['http', '6080', '--log=stdout']);

        // Wait for ngrok to provide URL
        for (let i = 0; i < 10; i++) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const res = await axios.get('http://localhost:4040/api/tunnels');
            const url = res.data.tunnels[0].public_url;
            if (url) return `${url}/vnc_lite.html?password=${vncPassword}`;
          } catch (e) {}
        }
      }
    } catch (err) {
      logger.error(`Tunnel setup failed: ${err.message}`);
    }
    return null;
  }

  stopUIStream() {
    logger.system('Engaging Low-Load Mode: Killing UI Stream processes...');
    if (this.ngrokProcess) this.ngrokProcess.kill();
    if (this.websockifyProcess) this.websockifyProcess.kill();
    if (this.vncProcess) this.vncProcess.kill();

    // Nuclear option to ensure ports are freed
    try {
      execSync('pkill -f ngrok || true');
      execSync('pkill -f websockify || true');
      execSync('pkill -f x11vnc || true');
    } catch (e) {}

    logger.success('Low-Load Mode Active. CPU usage minimized.');
  }
}

module.exports = new TunnelService();
