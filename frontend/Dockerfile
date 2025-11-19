FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install ALL dependencies (including devDependencies for build)
RUN npm ci

# Copy application files
COPY . .

# Build Next.js
RUN npm run build

# Expose port
EXPOSE 3000

# Set environment variable
ENV PORT=3000

# Run application
CMD ["npm", "start"]