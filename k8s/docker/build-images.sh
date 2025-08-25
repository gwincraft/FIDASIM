#!/bin/bash
# Build script for FIDASIM Kubernetes Docker images

set -e

REGISTRY=${DOCKER_REGISTRY:-"fidasim"}
VERSION=${VERSION:-"latest"}

echo "Building FIDASIM Docker images..."
echo "Registry: $REGISTRY"
echo "Version: $VERSION"

# Build controller image
echo "Building controller image..."
docker build -f controller.Dockerfile -t $REGISTRY/controller:$VERSION ..

# Build frontend image
echo "Building frontend image..."
docker build -f frontend.Dockerfile -t $REGISTRY/frontend:$VERSION ..

# Build results viewer image
echo "Building results viewer image..."
docker build -f results.Dockerfile -t $REGISTRY/results:$VERSION ..

# Build compute worker image
echo "Building compute worker image..."
docker build -f compute.Dockerfile -t $REGISTRY/compute:$VERSION ..

echo "All images built successfully!"

# Optional: Push to registry
if [ "$PUSH_IMAGES" = "true" ]; then
    echo "Pushing images to registry..."
    docker push $REGISTRY/controller:$VERSION
    docker push $REGISTRY/frontend:$VERSION
    docker push $REGISTRY/results:$VERSION
    docker push $REGISTRY/compute:$VERSION
    echo "Images pushed successfully!"
fi

echo "Build complete!"
echo ""
echo "To deploy to Kubernetes:"
echo "  kubectl apply -f ../deployment.yaml"
echo ""
echo "To push images to registry:"
echo "  PUSH_IMAGES=true ./build-images.sh"