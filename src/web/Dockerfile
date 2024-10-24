from node:20-slim
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

RUN pnpm install

# build project
RUN pnpm run build

RUN pnpm install -g serve

RUN pnpm install -g pm2

# expose port

EXPOSE 5000

# start service
CMD ["pm2-runtime", "ecosystem.config.js"]
