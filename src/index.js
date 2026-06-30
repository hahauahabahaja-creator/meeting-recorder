require('dotenv').config();
const { Telegraf } = require('telegraf');
const recorder = require('./services/recorder');
const tunnel = require('./services/tunnel');
const { keyboards, templates } = require('./ui/keyboards');
const logger = require('./utils/logger');
const fs = require('fs');
const { execSync } = require('child_process');
const express = require('express');

// Initialize Express for Render Port Binding
const app = express();
const PORT = process.env.PORT || 10000;
app.get('/', (req, res) => res.send('GHOST v3.0 is active.'));
app.get('/ping', (req, res) => res.send('pong'));
app.listen(PORT, () => console.log(`[SYSTEM] Port binding active on ${PORT}`));

let vosk = null; let wav = null;
try { vosk = require('vosk'); wav = require('wav'); } catch (e) { console.log("Native modules not loaded."); }

const bot = new Telegraf(process.env.TELEGRAM_BOT_TOKEN);

// Load Vosk Model (Free & Offline)
let model;
if (vosk) {
  try {
    vosk.setLogLevel(-1);
    model = new vosk.Model('model');
  } catch (e) {
    console.log("Vosk Model not found.");
  }
}

let activeFile = null;

// Middleware for authorization (Ultra-Robust Fix)
bot.use(async (ctx, next) => {
  const chatId = String(ctx.chat.id);
  const allowedGroup = String(process.env.ALLOWED_GROUP_ID || "");
  const personalId = String(process.env.TELEGRAM_CHAT_ID || "");

  // Check if either matches
  const isAuthorized = (chatId === allowedGroup) || (chatId === personalId);

  if (!isAuthorized) {
    // Helpful message for the user to find their ID
    if (ctx.chat.type === 'private') {
      return ctx.replyWithMarkdown(`? **Access Denied.**\n\nYour ID: \`${chatId}\` is not authorized.\n\n**To fix this:**\n1. Copy the ID above.\n2. Add it to GitHub Secrets as \`TELEGRAM_CHAT_ID\`.`);
    }
    return; // Ignore unauthorized groups
  }
  await next();
});

bot.start((ctx) => ctx.replyWithMarkdown(templates.welcome(ctx.from.first_name), keyboards.main()));

bot.command('join', async (ctx) => {
  const url = ctx.message.text.split(' ')[1];
  if (!url) return ctx.reply('?? Usage: /join <url>');
  const statusMsg = await ctx.reply('? Booting Ghost Engine...');
  try {
    await recorder.launchBrowser(url);
    const vncPassword = Math.random().toString(36).slice(-8);
    const vncUrl = await tunnel.startUIStream(vncPassword);
    if (vncUrl) {
      await ctx.telegram.editMessageText(ctx.chat.id, statusMsg.message_id, null, 
        `? **GHOST v3.0**\n????????????????????\n? **VNC Password:** \`${vncPassword}\`\n\n?? **ACTION REQUIRED:** Open the link. Login. Click **Engage Recording**.`,
        { parse_mode: 'Markdown', ...keyboards.controlPanel(vncUrl) }
      );
    }
  } catch (err) { ctx.reply(`? Boot Error: ${err.message}`); }
});

bot.action('cb_record', async (ctx) => {
  tunnel.stopUIStream();
  activeFile = recorder.startRecording();
  await ctx.editMessageText(`?? **LIVE RECORDING ACTIVE**\n????????????????????\n? **System Health:** Stable ?`, { parse_mode: 'Markdown', ...keyboards.recording() });
});

bot.action('cb_view', async (ctx) => {
  const path = await recorder.takeScreenshot();
  if (path) { await ctx.replyWithPhoto({ source: path }); fs.unlinkSync(path); }
});

bot.action('cb_stop', async (ctx) => {
  ctx.reply('? Finalizing and Wiping...');
  await recorder.stop();
  tunnel.stopUIStream();

  if (activeFile && fs.existsSync(activeFile)) {
    const fileSizeInMB = fs.statSync(activeFile).size / (1024 * 1024);
    await ctx.reply(`? Session Complete! (${fileSizeInMB.toFixed(1)} MB)`);
    
    if (fileSizeInMB < 45) {
      await ctx.replyWithDocument({ source: activeFile });
    } else {
      execSync(`ffmpeg -i ${activeFile} -c copy -f segment -segment_time 1200 -reset_timestamps 1 part_%03d.mp4`);
      const parts = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4')).sort();
      for (const p of parts) {
        await ctx.replyWithDocument({ source: p });
        fs.unlinkSync(p);
      }
    }

    if (model && vosk && wav) {
      ctx.reply('?? **AI Transcription:** Converting speech to text...');
      try {
        const audioWav = `audio_${Date.now()}.wav`;
        execSync(`ffmpeg -i ${activeFile} -ar 16000 -ac 1 ${audioWav}`);
        const wfReader = new wav.Reader();
        const readable = fs.createReadStream(audioWav);
        let fullText = "";
        await new Promise((resolve) => {
          wfReader.on('format', (format) => {
            const rec = new vosk.Recognizer({model: model, sampleRate: format.sampleRate});
            wfReader.on('data', (data) => { if (rec.acceptWaveform(data)) fullText += JSON.parse(rec.result()).text + " "; });
            wfReader.on('end', () => { fullText += JSON.parse(rec.finalResult()).text; rec.free(); resolve(); });
          });
          readable.pipe(wfReader);
        });
        const transcriptFile = `transcript_${Date.now()}.txt`;
        fs.writeFileSync(transcriptFile, `? GHOST TRANSCRIPTION\n\n${fullText}`);
        await ctx.replyWithDocument({ source: transcriptFile });
        fs.unlinkSync(audioWav);
        fs.unlinkSync(transcriptFile);
      } catch (e) {}
    }
    fs.unlinkSync(activeFile);
  }

  try {
    const repo = process.env.GITHUB_REPOSITORY;
    const token = process.env.PAT_TOKEN;
    const runId = process.env.GITHUB_RUN_ID;
    if (repo && token && runId) {
      execSync(`curl -L -X DELETE -H "Authorization: Bearer ${token}" https://api.github.com/repos/${repo}/actions/runs/${runId}`);
    }
  } catch (e) {}
});

bot.launch();
logger.success('GHOST v3.0 is Online.');
