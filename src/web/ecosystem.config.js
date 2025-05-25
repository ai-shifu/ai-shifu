require('dotenv').config();
module.exports = {
  apps: [
    {
      name: 'ai-shifu-web',
      // script: 'serve -s build -l '+(process.env.PORT || '5800'),
      script: 'node server.js',
      env: {
        PORT: process.env.PORT,
        REACT_APP_BASEURL: process.env.REACT_APP_BASEURL,
        REACT_APP_COURSE_ID: process.env.REACT_APP_COURSE_ID,
        REACT_APP_APP_ID: process.env.REACT_APP_APP_ID,
        REACT_APP_UMAMI_WEBSITE_ID: process.env.REACT_APP_UMAMI_WEBSITE_ID,
        REACT_APP_UMAMI_SCRIPT_SRC: process.env.REACT_APP_UMAMI_SCRIPT_SRC,

      },
    }
  ]
};
