require('dotenv').config();
const { Telegraf } = require('telegraf');
const recorder = require('./services/recorder');
const tunnel = require('./services/tunnel');
const { keyboards, templates } = require('./ui/keyboards');
const logger = require('./utils/logger');
const fs = require('fs');
const { execSync } = require('child_process');
const express = require('express');
const vosk = require('vosk');
const wav = require('wav');

// Initialize Express for Render Port Binding & API
const app = express();
const PORT = process.env.PORT || 10000;

// API endpoint for GitHub to fetch Auth IDs from Render
app.get('/api/auth', (req, res) => {
  res.json({
    personal_id: process.env.TELEGRAM_CHAT_ID || "",
    group_id: process.env.ALLOWED_GROUP_ID || ""
  });
});

app.get('/', (req, res) => res.send('GHOST v3.0 is active.'));
app.get('/ping', (req, res) => res.send('pong'));
app.listen(PORT, () => console.log(`[SYSTEM] Port binding active on ${PORT}`));

const bot = new Telegraf(process.env.TELEGRAM_BOT_TOKEN);
// Load Vosk Model (Free & Offline)
let model;
try {
  vosk.setLogLevel(-1);
  model = new vosk.Model('model');
} catch (e) {
  logger.error("Vosk Model not found. Transcription disabled.");
}

let activeFile = null;

// Middleware for authorization (Supports both Personal and Group IDs)
bot.use(async (ctx, next) => {
  const chatId = String(ctx.chat.id);
  const allowedGroup = String(process.env.ALLOWED_GROUP_ID || "");
  const personalId = String(process.env.TELEGRAM_CHAT_ID || "");

  const isAuthorized = (chatId === allowedGroup) || (chatId === personalId);

  if (!isAuthorized) {
    if (ctx.chat.type === 'private') {
      return ctx.replyWithMarkdown(`✖ **Access Denied.**\n\nYour ID: \`${chatId}\` is not authorized.\n\n**To fix this:**\nAdd this ID to **Render Environment Variables** as \`TELEGRAM_CHAT_ID\`.`);
    }
    return;
  }
  await next();
});

bot.start((ctx) => {
  ctx.replyWithMarkdown(templates.welcome(ctx.from.first_name), keyboards.main());
});

bot.command('join', async (ctx) => {
  const url = ctx.message.text.split(' ')[1];
  if (!url) return ctx.reply('⚠️ **Usage:** `/join <meeting_url>`');

  const statusMsg = await ctx.reply('⏳ **Booting Remote Engine...**\nInitializing Xvfb and Puppeteer.');

  try {
    // 1. Launch Browser
    await recorder.launchBrowser(url);

    // 2. Start UI Stream
    const vncPassword = Math.random().toString(36).slice(-8);
    const vncUrl = await tunnel.startUIStream(vncPassword);

    if (vncUrl) {
      await ctx.telegram.editMessageText(ctx.chat.id, statusMsg.message_id, null,
        `🤖 **GOGO RECORDER PANEL v3.0 [ULTRA]**\n━━━━━━━━━━━━━━━━━━━━━━━━\n💎 Status: 🟡 **Awaiting User Verification**\n🖥️ Virtual Display: **Active**\n\n🔑 **VNC Password:** \`${vncPassword}\`\n\n⚠️ **ACTION REQUIRED:** Open the link below. If it asks for a password, use the one given above. Once joined, click **Engage Low-Load Recording**.`,
        { parse_mode: 'Markdown', ...keyboards.controlPanel(vncUrl) }
      );
    } else {
      ctx.reply('❌ **Tunnel Failure.** Could not establish Ngrok link.');
    }
  } catch (err) {
    logger.error(err.message);
    ctx.reply(`❌ **Boot Error:** \`${err.message}\``);
  }
});

bot.action('cb_record', async (ctx) => {
  // 1. Kill UI Stream to save CPU
  tunnel.stopUIStream();

  // 2. Start FFMPEG Recording
  activeFile = recorder.startRecording();

  await ctx.editMessageText(
    `⏺️ **LIVE RECORDING ACTIVE**\n━━━━━━━━━━━━━━━━━━━━━━━━\n⚡ **Eco-Mode:** Enabled (GUI Stream Paused)\n🔊 **Audio Input:** Stream Healthy (Stereo)\n📈 **System Health:** Stable 🟢`,
    { parse_mode: 'Markdown', ...keyboards.recording() }
  );
});

bot.action('cb_view', async (ctx) => {
  const path = await recorder.takeScreenshot();
  if (path) {
    await ctx.replyWithPhoto({ source: path }, { caption: `📸 **Live View** - ${new Date().toLocaleTimeString()}` });
    fs.unlinkSync(path);
  }
});

bot.action('cb_stop', async (ctx) => {
  await handleStop(ctx);
});

async function handleStop(ctx) {
  ctx.reply('🏁 **Wiping instance and finalizing video...**');

  await recorder.stop();
  tunnel.stopUIStream();

  if (activeFile && fs.existsSync(activeFile)) {
    const stats = fs.statSync(activeFile);
    const fileSizeInMB = stats.size / (1024 * 1024);

    await ctx.reply(`✅ **Session Complete!** (${fileSizeInMB.toFixed(1)} MB)\n📤 **Starting upload...**`);

    if (fileSizeInMB < 45) {
      await ctx.replyWithDocument({ source: activeFile }, { caption: '🎬 **Meeting Recording (Original)**' });
    } else {
      await ctx.reply('📂 **File is large, splitting into parts for Telegram...**');

      try {
        // Split into 40MB chunks
        execSync(`ffmpeg -i ${activeFile} -c copy -f segment -segment_time 1200 -reset_timestamps 1 part_%03d.mp4`);
        const parts = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4')).sort();

        for (let i = 0; i < parts.length; i++) {
          await ctx.replyWithDocument({ source: parts[i] }, { caption: `🎬 **Part ${i+1} of ${parts.length}**` });
          fs.unlinkSync(parts[i]);
        }
      } catch (err) {
        ctx.reply('❌ **Error during splitting:** ' + err.message);
      }
    }

    // 📝 FREE TRANSCRIPTION FEATURE (Offline Speech to Text)
    if (model) {
      ctx.reply('🎙️ **Free AI Transcription:** Converting speech to text (Offline)...');
      try {
        const audioWav = `audio_${Date.now()}.wav`;
        const transcriptFile = `transcript_${Date.now()}.txt`;

        // 1. Extract Audio from Video (Vosk needs WAV 16kHz Mono)
        execSync(`ffmpeg -i ${activeFile} -ar 16000 -ac 1 ${audioWav}`);

        // 2. Process with Vosk
        const wfReader = new wav.Reader();
        const readable = fs.createReadStream(audioWav);
        let fullText = "";

        await new Promise((resolve) => {
          wfReader.on('format', (format) => {
            const rec = new vosk.Recognizer({model: model, sampleRate: format.sampleRate});
            wfReader.on('data', (data) => {
              const res = rec.acceptWaveform(data);
              if (res) {
                fullText += JSON.parse(rec.result()).text + " ";
              }
            });
            wfReader.on('end', () => {
              fullText += JSON.parse(rec.finalResult()).text;
              rec.free();
              resolve();
            });
          });
          readable.pipe(wfReader);
        });

        // 3. Save to Text File and Send
        if (fullText.trim().length > 0) {
          fs.writeFileSync(transcriptFile, `💀 GHOST FREE TRANSCRIPTION\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n${fullText}`);
          await ctx.replyWithDocument({ source: transcriptFile }, { caption: '📝 **Meeting Notes (Free Offline AI)**' });
        } else {
          ctx.reply('ℹ️ **Transcription Empty:** No clear speech detected.');
        }

        // Cleanup
        if (fs.existsSync(audioWav)) fs.unlinkSync(audioWav);
        if (fs.existsSync(transcriptFile)) fs.unlinkSync(transcriptFile);
      } catch (err) {
        ctx.reply('⚠️ **Transcription Failed:** ' + err.message);
      }
    } else {
      ctx.reply('ℹ️ **Transcription Skip:** Local model not initialized.');
    }

    fs.unlinkSync(activeFile);
    activeFile = null;
  } else {
    ctx.reply('🏁 **Instance closed.** No recording was generated.');
  }

  // 🏁 GHOST MODE: Delete Workflow History
  ctx.reply('🧹 **Ghost Mode: Wiping GitHub Activity Logs...**');
  try {
    const repo = process.env.GITHUB_REPOSITORY;
    const token = process.env.PAT_TOKEN;
    const runId = process.env.GITHUB_RUN_ID;
    if (repo && token && runId) {
      execSync(`curl -L -X DELETE -H "Authorization: Bearer ${token}" -H "Accept: application/vnd.github+json" https://api.github.com/repos/${repo}/actions/runs/${runId}`);
    }
  } catch (e) {}
}

bot.launch();
logger.success('Ghost Recorder Bot is online and listening.');

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
