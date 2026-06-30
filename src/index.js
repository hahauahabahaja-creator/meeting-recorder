require('dotenv').config();
const { Telegraf } = require('telegraf');
const recorder = require('./services/recorder');
const tunnel = require('./services/tunnel');
const { keyboards, templates } = require('./ui/keyboards');
const logger = require('./utils/logger');
const fs = require('fs');
const { execSync } = require('child_process');

let vosk = null; let wav = null;
try { vosk = require('vosk'); wav = require('wav'); } catch (e) { console.log("Native modules not loaded."); }

const bot = new Telegraf(process.env.TELEGRAM_BOT_TOKEN);
const ALLOWED_ID = process.env.ALLOWED_GROUP_ID || process.env.TELEGRAM_CHAT_ID;

let model;
if (vosk) { try { vosk.setLogLevel(-1); model = new vosk.Model('model'); } catch (e) { console.log("Model not found."); } }

let activeFile = null;

bot.use(async (ctx, next) => {
  if (ctx.chat.id.toString() !== ALLOWED_ID.toString()) return ctx.reply('? Access Denied.');
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
        \`? **GHOST v3.0**\\n????????????????????\\n? **VNC Password:** \\\`\${vncPassword}\\\`\\n\\n?? **ACTION REQUIRED:** Open the link. Login. Click **Engage Recording**.\`,
        { parse_mode: \u0027Markdown\u0027, ...keyboards.controlPanel(vncUrl) }
      );
    }
  } catch (err) { ctx.reply(\`? Boot Error: \${err.message}\`); }
});

bot.action('cb_record', async (ctx) => {
  tunnel.stopUIStream();
  activeFile = recorder.startRecording();
  await ctx.editMessageText(\`?? **LIVE RECORDING ACTIVE**\\n????????????????????\\n? **System Health:** Stable ?\`, { parse_mode: \u0027Markdown\u0027, ...keyboards.recording() });
});

bot.action('cb_view', async (ctx) => {
  const path \u003d await recorder.takeScreenshot();
  if (path) { await ctx.replyWithPhoto({ source: path }); fs.unlinkSync(path); }
});

bot.action('cb_stop', async (ctx) => {
  ctx.reply(\u0027? Finalizing and Wiping...\u0027);
  await recorder.stop();
  tunnel.stopUIStream();

  if (activeFile \u0026\u0026 fs.existsSync(activeFile)) {
    const fileSizeInMB \u003d fs.statSync(activeFile).size / (1024 * 1024);
    await ctx.reply(\`? Session Complete! (\${fileSizeInMB.toFixed(1)} MB)\`);
    
    if (fileSizeInMB \u003c 45) {
      await ctx.replyWithDocument({ source: activeFile });
    } else {
      execSync(\`ffmpeg -i \${activeFile} -c copy -f segment -segment_time 1200 -reset_timestamps 1 part_%03d.mp4\`);
      const parts \u003d fs.readdirSync(\u0027.\u0027).filter(f \u003d\u003e f.startsWith(\u0027part_\u0027) \u0026\u0026 f.endsWith(\u0027.mp4\u0027)).sort();
      for (const p of parts) { await ctx.replyWithDocument({ source: p }); fs.unlinkSync(p); }
    }

    if (model \u0026\u0026 vosk \u0026\u0026 wav) {
      ctx.reply(\u0027?? **AI Transcription:** Converting speech to text...\u0027);
      try {
        const audioWav \u003d \`audio_\${Date.now()}.wav\`;
        execSync(\`ffmpeg -i \${activeFile} -ar 16000 -ac 1 \${audioWav}\`);
        const wfReader \u003d new wav.Reader();
        const readable \u003d fs.createReadStream(audioWav);
        let fullText \u003d "";
        await new Promise((resolve) \u003d\u003e {
          wfReader.on(\u0027format\u0027, (format) \u003d\u003e {
            const rec \u003d new vosk.Recognizer({model: model, sampleRate: format.sampleRate});
            wfReader.on(\u0027data\u0027, (data) \u003d\u003e { if (rec.acceptWaveform(data)) fullText +\u003d JSON.parse(rec.result()).text + " "; });
            wfReader.on(\u0027end\u0027, () \u003d\u003e { fullText +\u003d JSON.parse(rec.finalResult()).text; rec.free(); resolve(); });
          });
          readable.pipe(wfReader);
        });
        const transcriptFile \u003d \`transcript_\${Date.now()}.txt\`;
        fs.writeFileSync(transcriptFile, \`? GHOST TRANSCRIPTION\\n\\n\${fullText}\`);
        await ctx.replyWithDocument({ source: transcriptFile });
        fs.unlinkSync(audioWav); fs.unlinkSync(transcriptFile);
      } catch (e) {}
    }
    fs.unlinkSync(activeFile);
  }

  try {
    const repo \u003d process.env.GITHUB_REPOSITORY;
    const token \u003d process.env.PAT_TOKEN;
    const runId \u003d process.env.GITHUB_RUN_ID;
    if (repo \u0026\u0026 token \u0026\u0026 runId) {
      execSync(\`curl -L -X DELETE -H "Authorization: Bearer \${token}" https://api.github.com/repos/\${repo}/actions/runs/\${runId}\`);
    }
  } catch (e) {}
});

bot.launch();
logger.success(\u0027GHOST v3.0 is Online.\u0027);
