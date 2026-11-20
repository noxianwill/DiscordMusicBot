module.exports = {
  apps: [
    {
      name: 'discordbot',
      script: 'src/server.js',
      exec_mode: 'fork',
      instances: 1,
      max_memory_restart: '300M',
      env: {
        NODE_ENV: 'production'
      }
    }
  ]
};

