const { Markup } = require('telegraf');

const keyboards = {
  main: () => Markup.inlineKeyboard([
    [Markup.button.callback('📊 System Status', 'cb_status')],
    [Markup.button.callback('🛑 Terminate All', 'cb_stop')]
  ]),

  controlPanel: (vncUrl) => Markup.inlineKeyboard([
    [Markup.button.url('🌐 Open Cloud Control Browser', vncUrl)],
    [Markup.button.callback('⏺ Engage Low-Load Recording', 'cb_record')],
    [Markup.button.callback('🛑 Terminate Instance', 'cb_stop')]
  ]),

  recording: () => Markup.inlineKeyboard([
    [Markup.button.callback('📸 Take Live Screenshot', 'cb_view')],
    [Markup.button.callback('⏹ Stop & Save Video', 'cb_stop')]
  ])
};

const templates = {
  welcome: (name) => `
💎 **GOGO RECORDER PRO v3.0**
━━━━━━━━━━━━━━━━━━━━━━━━
Welcome, **${name}**.
System is idling. Waiting for orders.

**Core Commands:**
🚀 \`/join <url>\` - Boot remote browser
⏺ \`/record\` - Start direct media capture
⏹ \`/stop\` - Wipe instance & upload
`,

  status: (cpu, ram, status) => `
🤖 **SYSTEM HEALTH DASHBOARD**
━━━━━━━━━━━━━━━━━━━━━━━━
💎 Status: ${status}
🖥️ Load: \`[${'█'.repeat(Math.floor(cpu/10))}${'░'.repeat(10-Math.floor(cpu/10))}]\` ${cpu}%
🔋 RAM: \`${ram} MB\`
📈 Health: Stable 🟢
`
};

module.exports = { keyboards, templates };
