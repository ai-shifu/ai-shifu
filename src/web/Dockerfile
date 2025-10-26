FROM node:20.11.1 AS base
# use pnpm
RUN corepack enable
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"


# set work directory
WORKDIR /usr/src/app

# install project dependencies
# copy package.json and package-lock.json files
COPY package*.json ./

# copy ecosystem.config.js file
COPY ecosystem.config.js ./

# copy project source code
COPY . .

# Configure git to use HTTPS instead of SSH for GitHub
RUN git config --global url."https://github.com/".insteadOf "git@github.com:"

# Clean lock file to avoid SSH URL issues and reinstall
RUN rm -f pnpm-lock.yaml && pnpm install

# build project
RUN pnpm run build

FROM node:20.11.1-slim

WORKDIR /app
COPY ecosystem.config.js ./
COPY --from=base /usr/src/app/build ./build
COPY server.js ./
RUN npm install -g pm2
RUN npm install express
RUN npm install dotenv

# expose port
EXPOSE 5000

# start service
CMD ["pm2-runtime", "ecosystem.config.js"]
