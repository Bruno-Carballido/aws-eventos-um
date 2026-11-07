@echo off
setlocal enabledelayedexpansion

set REGION=%AWS_REGION%
if "%REGION%"=="" set REGION=us-east-1
set REPO_NAME=aws-eventos-um-backend

echo === Compilacion y publicacion de contenedor ECS en Amazon ECR ===

if "%ACCOUNT_ID%"=="" (
    for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text') do set ACCOUNT_ID=%%i
)

set ECR_URI=%ACCOUNT_ID%.dkr.ecr.%REGION%.amazonaws.com/%REPO_NAME%:latest

echo Region:     %REGION%
echo Account ID: %ACCOUNT_ID%
echo Imagen URI: %ECR_URI%

echo 1. Autenticando con Amazon ECR...
aws ecr get-login-password --region %REGION% | docker login --username AWS --password-stdin %ACCOUNT_ID%.dkr.ecr.%REGION%.amazonaws.com
if errorlevel 1 goto error

echo 2. Compilando la imagen Docker...
docker build -t %REPO_NAME% src\
if errorlevel 1 goto error

echo 3. Etiquetando la imagen...
docker tag %REPO_NAME%:latest %ECR_URI%
if errorlevel 1 goto error

echo 4. Subiendo imagen a ECR...
docker push %ECR_URI%
if errorlevel 1 goto error

echo === Imagen subida con exito ===
echo URI para parametro CloudFormation ImagenBackend:
echo %ECR_URI%
goto end

:error
echo [ERROR] Ocurrio un error durante la ejecucion del script.
exit /b 1

:end
endlocal
