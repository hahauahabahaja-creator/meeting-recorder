const { Markup } = require('telegraf');

const keyboards = {
  main: () => Markup.inlineKeyboard([
    [Markup.button.callback('? System Status', 'cb_status')],
    [Markup.button.callback('? Terminate All', 'cb_stop')]
  ]),

  controlPanel: (vncUrl) => Markup.inlineKeyboard([
    [Markup.button.url('? Open Cloud Control Browser', vncUrl)],
    [Markup.button.callback('? Engage Low-Load Recording', 'cb_record')],
    [Markup.button.callback('? Terminate Instance', 'cb_stop')]
  ]),

  recording: () => Markup.inlineKeyboard([
    [Markup.button.callback('? Take Live Screenshot', 'cb_view')],
    [Markup.button.callback('? Stop & Save Video', 'cb_stop')]
  ])
};

const templates = {
  welcome: (name) => `
? **GHOST v3.0**
????????????????????
Welcome, **${name}**.
`,

  status: (cpu, ram, status) => `
? **GHOST DASHBOARD**
????????????????????
Status: ${status}
RAM: ${ram} MB
`
};

module.exports = { keyboards, templates };
