# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
ARG VITE_PANEL_PATH=panel
ENV VITE_PANEL_PATH=$VITE_PANEL_PATH
RUN npm run build

FROM nginx:1.27-alpine AS runtime
# nginx proxies /api to the backend, so the browser sees one origin: no CORS,
# and the admin token never crosses an origin boundary.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
