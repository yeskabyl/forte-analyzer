#!/usr/bin/env bash
# Разворачивает бэкенд на чистом сервере Ubuntu 22.04/24.04 (например, DigitalOcean Droplet).
# Запуск на сервере под root:
#
#   curl -fsSL https://raw.githubusercontent.com/yeskabyl/forte-analyzer/main/deploy/setup-server.sh | bash
#
# Повторный запуск безопасен: подтягивает свежий код из GitHub и перезапускает контейнеры,
# .env (домен и API-ключ) сохраняется.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/yeskabyl/forte-analyzer.git}"
APP_DIR="${APP_DIR:-/opt/forte-analyzer}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите под root (или через sudo)." >&2
  exit 1
fi

# 1. Swap: сборка образов (opencv, numpy) на сервере с 1-2 ГБ RAM иначе может упасть по памяти.
if ! swapon --show | grep -q .; then
  echo "==> Создаю swap 2 ГБ"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2. Docker + compose plugin.
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Устанавливаю Docker"
  curl -fsSL https://get.docker.com | sh
fi
command -v git >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq git; }

# 3. Firewall: SSH и HTTP(S) для Caddy. Порт API наружу не публикуется (docker-compose.prod.yml).
if command -v ufw >/dev/null 2>&1; then
  echo "==> Настраиваю firewall"
  ufw allow OpenSSH >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw allow 443/udp >/dev/null
  ufw --force enable >/dev/null
fi

# 4. Код.
if [ -d "$APP_DIR/.git" ]; then
  echo "==> Обновляю код в $APP_DIR"
  git -C "$APP_DIR" pull --ff-only
else
  echo "==> Клонирую $REPO_URL в $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# 5. .env: домен <ip>.sslip.io (бесплатный DNS, указывает на IP сервера) и случайный API-ключ.
if [ ! -f .env ]; then
  IP="$(curl -fsS --max-time 5 http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address \
        || curl -fsS --max-time 10 https://api.ipify.org)"
  DOMAIN="${DOMAIN:-${IP//./-}.sslip.io}"
  cat > .env <<EOF
DOMAIN=${DOMAIN}
API_KEY=$(openssl rand -hex 24)
CORS_ORIGINS=https://forte-analyzer.vercel.app,http://localhost:5173,http://localhost:3000
MAX_UPLOAD_MB=500
EOF
  chmod 600 .env
  echo "==> Создан .env (домен ${DOMAIN})"
fi

# 6. Запуск.
echo "==> Собираю и запускаю контейнеры (первый раз — несколько минут)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans

# shellcheck disable=SC1091
. ./.env
echo "==> Жду HTTPS-сертификат для ${DOMAIN}"
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "https://${DOMAIN}/docs"; then
    break
  fi
  sleep 4
done

cat <<EOF

Готово.
  API:      https://${DOMAIN}
  Swagger:  https://${DOMAIN}/docs
  API-ключ: ${API_KEY}

Дальше: в Vercel (Project → Settings → Environment Variables) задайте
  VITE_API_BASE_URL = https://${DOMAIN}
и сделайте Redeploy. API-ключ вводится в поле X-API-Key на сайте.
Логи: cd ${APP_DIR} && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
EOF
