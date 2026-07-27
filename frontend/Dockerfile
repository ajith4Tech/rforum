FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# adapter-static (svelte.config.js) writes the SPA to build/ — same output
# nginx serves directly from disk in the current bare-metal deployment.
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i 's/user  nginx;//' /etc/nginx/nginx.conf \
    && sed -i '/^pid/d' /etc/nginx/nginx.conf \
    && touch /var/run/nginx.pid \
    && chown -R 101:101 /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html /etc/nginx/conf.d
USER 101
EXPOSE 8080
