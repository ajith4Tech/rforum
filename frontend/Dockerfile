FROM node:20-alpine AS builder
WORKDIR /app

# 1. Copy package files and install ALL dependencies
COPY package*.json ./
RUN npm install

# 2. Copy the rest of the source
COPY . .

# 3. Generate SvelteKit types/internal files and then build
# This fixes the "Cannot find base config file" warning
RUN npx svelte-kit sync
RUN CI=false npm run build

# Stage 2: Production
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy only the built app and production modules
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000
ENV PORT=3000

CMD ["node", "build/index.js"]