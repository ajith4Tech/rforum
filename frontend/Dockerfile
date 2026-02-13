# Use a specific node version for stability
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for better caching
COPY package*.json ./
RUN npm install

# Copy the rest of the frontend source
COPY . .

# Build the SvelteKit app
RUN npm run build

# Use a lean runtime image for production
FROM node:20-alpine AS runner
WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Copy built files and production dependencies from builder
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules

# Railway provides the PORT environment variable at runtime
EXPOSE 3000
ENV PORT=3000

# Start the server using the compiled index.js
CMD ["node", "build/index.js"]