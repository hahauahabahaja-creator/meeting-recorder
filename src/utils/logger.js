const logger = {
  info: (msg) => console.log(`\x1b[34m?\x1b[0m [${new Date().toLocaleTimeString()}] ${msg}`),
  success: (msg) => console.log(`\x1b[32m?\x1b[0m [${new Date().toLocaleTimeString()}] ${msg}`),
  warn: (msg) => console.log(`\x1b[33m?\x1b[0m [${new Date().toLocaleTimeString()}] ${msg}`),
  error: (msg) => console.error(`\x1b[31m?\x1b[0m [${new Date().toLocaleTimeString()}] ${msg}`),
  system: (msg) => console.log(`\x1b[35m?\x1b[0m [${new Date().toLocaleTimeString()}] \x1b[1m${msg}\x1b[0m`)
};

module.exports = logger;
