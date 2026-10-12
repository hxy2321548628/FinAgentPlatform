#!/usr/bin/env bash
# Docker Hub 无法访问时，预下载 Docker 在 ECR 发布的官方镜像。
set -euo pipefail
for image in docker:27-cli nginx:1.27-alpine node:24-bookworm-slim postgres:16-alpine redis:7-alpine; do
    docker pull "public.ecr.aws/docker/library/$image"
    docker tag "public.ecr.aws/docker/library/$image" "$image"
done
