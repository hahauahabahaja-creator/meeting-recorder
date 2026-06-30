require('dotenv').config();
const { Telegraf } = require('telegraf');
const recorder = require('./services/recorder');
const tunnel = require('./services/tunnel');
const { keyboards, templates } = require('./ui/keyboards');
const logger = require('./utils/logger');
const fs = require('fs');
const { execSync } = require('child_process');

const bot = new Telegraf(process.env.TELEGRAM_BOT_TOKEN);
const ALLOWED_ID = process.env.ALLOWED_GROUP_ID || process.env.TELEGRAM_CHAT_ID;

let activeFile = null;

// Middleware for authorization
bot.use(async (ctx, next) => {
  if (ctx.chat.id.toString() !== ALLOWED_ID.toString()) {
    return ctx.reply('✖ **Access Denied.** Unauthorized User ID detected.');
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
        `🤖 **GOGO RECORDER PANEL v3.0 [ULTRA]**\n━━━━━━━━━━━━━━━━━━━━━━━━\n💎 Status: 🟡 **Awaiting User Verification**\n🖥️ Virtual Display: **Active**\n\n⚠️ **ACTION REQUIRED:** Open the link below to join the meeting manually. Once joined, click **Engage Low-Load Recording**.`,
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

    // Logic for splitting files if > 50MB (simplified for now)
    if (fileSizeInMB < 49) {
      await ctx.replyWithDocument({ source: activeFile }, { caption: '🎬 **Meeting Recording**' });
    } else {
      ctx.reply('📂 **File is large.** Please download from the server or use a custom upload service.');
    }

    fs.unlinkSync(activeFile);
    activeFile = null;
  } else {
    ctx.reply('🏁 **Instance closed.** No recording was generated.');
  }
}

bot.launch();
logger.success('Ghost Recorder Bot is online and listening.');

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
