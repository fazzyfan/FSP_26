FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# Dev-режим: Vite с прокси /api на backend (внутри docker-сети)
CMD ["sh", "-c", "VITE_PROXY_TARGET=${VITE_PROXY_TARGET:-http://api:8000} npm run dev"]