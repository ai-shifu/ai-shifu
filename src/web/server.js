const express = require('express');
require('dotenv').config();
const app = express();
const port = process.env.PORT || 3000;
const path = require('path');

app.post('/config/env', (req, res) => {
  res
    .set('Cache-Control', 'no-cache')
    .json({
      'REACT_APP_BASEURL': process.env.REACT_APP_BASEURL || '/',
      'REACT_APP_UMAMI_SCRIPT_SRC': process.env.REACT_APP_UMAMI_SCRIPT_SRC  || '',
      'REACT_APP_UMAMI_WEBSITE_ID': process.env.REACT_APP_UMAMI_WEBSITE_ID || '',
      'REACT_APP_COURSE_ID': process.env.REACT_APP_COURSE_ID || '',
      'REACT_APP_ALWAYS_SHOW_LESSON_TREE': process.env.REACT_APP_ALWAYS_SHOW_LESSON_TREE || false,
      'REACT_APP_APP_ID': process.env.REACT_APP_APP_ID || '',
      'REACT_APP_ERUDA': process.env.REACT_APP_ERUDA || false,
      'REACT_APP_LOGO_HORIZONTAL': process.env.REACT_APP_LOGO_HORIZONTAL || '',
      'REACT_APP_LOGO_VERTICAL': process.env.REACT_APP_LOGO_VERTICAL || '',
      'REACT_APP_ENABLE_WXCODE': process.env.REACT_APP_ENABLE_WXCODE !== undefined ? process.env.REACT_APP_ENABLE_WXCODE === 'true' : true,
      'REACT_APP_SITE_URL': process.env.REACT_APP_SITE_URL || '/',
    });
});
// // Serve static files from the React app
app.use(express.static(path.join(__dirname, 'build')));

app.get(/^\/.*$/, (reg, res) => {
  res.sendFile(path.join(__dirname, 'build', 'index.html'));
});
app.listen(port, () => {
});
