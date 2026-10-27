FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/extension/package.json apps/extension/package.json
RUN npm ci
COPY apps/web apps/web
RUN npm run build

FROM nginx:1.28-alpine
COPY infra/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
RUN chmod a+r /etc/nginx/nginx.conf && chmod -R a+rX /usr/share/nginx/html
USER nginx
EXPOSE 8080
