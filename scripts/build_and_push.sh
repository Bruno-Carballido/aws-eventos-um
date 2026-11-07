#!/usr/bin/env bash
set -e

# Configuración por defecto
REGION=${AWS_REGION:-"us-east-1"}
REPO_NAME="aws-eventos-um-backend"

echo "=== Compilación y publicación de contenedor ECS en Amazon ECR ==="

# Obtener Account ID si no se proveyó
if [ -z "$ACCOUNT_ID" ]; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
fi

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}:latest"

echo "Región:     $REGION"
echo "Account ID: $ACCOUNT_ID"
echo "Imagen URI: $ECR_URI"

# 1. Login en ECR
echo "1. Autenticando con Amazon ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# 2. Build de la imagen Docker
echo "2. Compilando la imagen Docker..."
docker build -t "$REPO_NAME" src/

# 3. Taggear la imagen
echo "3. Etiquetando la imagen..."
docker tag "${REPO_NAME}:latest" "$ECR_URI"

# 4. Push a ECR
echo "4. Subiendo imagen a ECR..."
docker push "$ECR_URI"

echo "=== Imagen subida con éxito ==="
echo "URI para parámetro CloudFormation ImagenBackend:"
echo "$ECR_URI"
