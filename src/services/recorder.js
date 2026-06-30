const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const { spawn } = require('child_process');
const logger = require('../utils/logger');
const fs = require('fs');

puppeteer.use(StealthPlugin());

class RecorderService {
  constructor() {
    this.browser = null;
    this.page = null;
    this.ffmpegProcess = null;
    this.isRecording = false;
  }

  async launchBrowser(url) {
    logger.info(`Launching isolated browser for: ${url}`);
    this.browser = await puppeteer.launch({
      headless: false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        '--window-size=1920,1080',
        '--display=:99'
      ],
      defaultViewport: { width: 1920, height: 1080 }
    });

    this.page = await this.browser.newPage();
    await this.page.goto(url, { waitUntil: 'networkidle2' });

    // Auto-Admit / Click Join Logic
    setTimeout(async () => {
      try {
        const joinSelectors = [
          'button:has-text("Join now")',
          'button:has-text("Ask to join")',
          '[aria-label="Join now"]'
        ];
        for (const selector of joinSelectors) {
          if (await this.page.$(selector)) {
            await this.page.click(selector);
            logger.success('Auto-Join: Clicked join button.');
            break;
          }
        }
      } catch (e) {}
    }, 10000);

    return this.page;
  }

  startRecording() {
    if (this.isRecording) return;

    const timestamp = Date.now();
    const outputFile = `recording_${timestamp}.mp4`;
    logger.system(`Starting Zero-Lag FFMPEG Pipe: ${outputFile}`);

    // Optimized FFMPEG command for High-Quality 1080p
    // High Bitrate and slower preset for better clarity
    this.ffmpegProcess = spawn('ffmpeg', [
      '-y',
      '-f', 'x11grab',
      '-video_size', '1920x1080',
      '-framerate', '30',
      '-i', ':99',
      '-f', 'pulse',
      '-i', 'default',
      '-c:v', 'libx264',
      '-preset', 'medium', // Better quality than ultrafast
      '-crf', '20',        // Lower CRF = Higher Quality
      '-pix_fmt', 'yuv420p',
      '-c:a', 'aac',
      '-b:a', '192k',      // Higher Audio Bitrate
      outputFile
    ]);

    this.isRecording = true;
    return outputFile;
  }

  async stop() {
    logger.info('Stopping all services and browser...');

    if (this.ffmpegProcess) {
      this.ffmpegProcess.stdin.write('q');
      await new Promise(r => setTimeout(r, 5000));
      this.ffmpegProcess.kill('SIGINT');
    }

    if (this.browser) {
      await this.browser.close();
    }

    this.isRecording = false;
    this.browser = null;
    this.page = null;
  }

  async takeScreenshot() {
    if (!this.page) return null;
    const path = `screenshot_${Date.now()}.png`;
    await this.page.screenshot({ path });
    return path;
  }
}

module.exports = new RecorderService();
