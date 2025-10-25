#!/bin/bash

# Build script for optimized cook-web Docker image

echo "Building optimized cook-web Docker image..."

# Build the optimized image
docker build -f Dockerfile.optimized -t cook-web:optimized .

# Get image size
echo "Image size:"
docker images cook-web:optimized --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Compare with original if it exists
if docker images cook-web:latest >/dev/null 2>&1; then
    echo "Comparison with original image:"
    docker images cook-web --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
fi

echo "Build completed!"
