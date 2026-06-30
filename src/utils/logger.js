const chalk = require('chalk');

const logger = {
  info: (msg) => console.log(`${chalk.blue('ℹ')} [${new Date().toLocaleTimeString()}] ${msg}`),
  success: (msg) => console.log(`${chalk.green('✔')} [${new Date().toLocaleTimeString()}] ${msg}`),
  warn: (msg) => console.log(`${chalk.yellow('⚠')} [${new Date().toLocaleTimeString()}] ${msg}`),
  error: (msg) => console.error(`${chalk.red('✖')} [${new Date().toLocaleTimeString()}] ${msg}`),
  system: (msg) => console.log(`${chalk.magenta('⚙')} [${new Date().toLocaleTimeString()}] ${chalk.bold(msg)}`)
};

module.exports = logger;
