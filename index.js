const express = require('express');
const path = require('path');

const app = express();
const PORT = parseInt(process.env.PORT, 10) || 10000;

// Serve static files from the "public" folder
app.use(express.static(path.join(__dirname, 'public')));

// Fallback route for single-page app (serve index.html for any non-static route)
app.get('*', (req, res) => {
  res.sendFile(path.resolve(__dirname, 'public', 'index.html'), (err) => {
    if (err) {
      console.error('Error sending index.html:', err);
      res.status(err.status || 500).send('Server error');
    }
  });
});

// Start the server with graceful shutdown support
const server = app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

function shutdown(signal) {
  console.log(`Received ${signal}. Shutting down...`);
  server.close((err) => {
    if (err) {
      console.error('Error during server close', err);
      process.exit(1);
    }
    process.exit(0);
  });
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

// Export app for testing
module.exports = app;