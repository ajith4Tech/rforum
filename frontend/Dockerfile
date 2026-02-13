FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source and build
COPY . .
RUN ls -la src/lib && ls -la src/lib/api.ts
RUN npm run build

EXPOSE 4173

ENV PORT=4173

# Use PORT provided by the platform when available (Railway sets PORT)
CMD ["sh", "-c", "npm run preview -- --host 0.0.0.0 --port ${PORT:-4173}"]
