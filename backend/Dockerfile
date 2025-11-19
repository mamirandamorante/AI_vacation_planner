FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --omit=dev

# Copy application
COPY server.js .

# Set environment variables
ENV PORT=8080

# Expose port
EXPOSE 8080

# Run application
CMD ["node", "server.js"]