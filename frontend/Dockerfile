FROM node:20-alpine AS builder
WORKDIR /app

# Only copy package files first to leverage Docker cache
COPY package*.json ./
# Use 'npm ci' for a clean, automated install based on lockfile
RUN npm ci 

COPY . .

# Run build with CI=false to ignore non-critical warnings
RUN CI=false npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy only production essentials
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000
ENV PORT=3000

CMD ["node", "build/index.js"]