# Base images pinned by digest so upstream tag republishes don't silently
# invalidate the npm ci / build cache. Bump deliberately to pick up patches.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# adapter-static (svelte.config.js) writes the SPA to build/ — same output
# nginx serves directly from disk in the current bare-metal deployment.
RUN npm run build

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
# --chown on the COPYs rather than in the chown -R below: chowning the
# copied SPA in a later RUN duplicated all of it into a second layer.
COPY --chown=101:101 --from=build /src/build /usr/share/nginx/html
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's/user  nginx;//' /etc/nginx/nginx.conf \
    && sed -i '/^pid/d' /etc/nginx/nginx.conf \
    && touch /var/run/nginx.pid \
    && chown 101:101 /usr/share/nginx/html \
    && chown -R 101:101 /var/run/nginx.pid /var/cache/nginx /etc/nginx/conf.d
USER 101
EXPOSE 8080
