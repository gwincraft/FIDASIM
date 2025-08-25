# FIDASIM Frontend Service Docker Image
FROM nginx:alpine

# Install runtime dependencies
RUN apk add --no-cache \
    curl \
    tzdata

# Copy nginx configuration
COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY frontend/default.conf /etc/nginx/conf.d/default.conf

# Copy frontend files
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/static /usr/share/nginx/html/static

# Create directories for file uploads
RUN mkdir -p /usr/share/nginx/html/uploads && \
    chmod 755 /usr/share/nginx/html/uploads

# Add health check endpoint
RUN echo "OK" > /usr/share/nginx/html/health

# Set proper permissions
RUN chown -R nginx:nginx /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Run nginx
CMD ["nginx", "-g", "daemon off;"]