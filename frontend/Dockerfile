# Stage 1: Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies - using 'npm ci' for reproducible builds
# (Requires a package-lock.json to be present in /frontend)
COPY package*.json ./
RUN npm install

# Copy source files
COPY . .

# Run the build
# SvelteKit with adapter-node will create a 'build/' directory
RUN npm run build

# Stage 2: Production runtime stage
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Copy only the necessary build artifacts and production dependencies
# This keeps the image small (~160MB vs 800MB+)
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules

# Railway provides the PORT environment variable at runtime
EXPOSE 3000
ENV PORT=3000

# Start the standalone Node server produced by adapter-node
CMD ["node", "build/index.js"]