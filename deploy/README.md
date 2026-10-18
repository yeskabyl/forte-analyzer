# Деплой бэкенда на DigitalOcean

Бэкенд (API + Celery-воркер + Redis) работает на сервере 24/7, интерфейс остаётся на Vercel.
HTTPS — через Caddy с бесплатным сертификатом Let's Encrypt; свой домен не нужен,
используется `<ip-сервера>.sslip.io`.

> Видео, которые загружают на сайт, обрабатываются на этом сервере. Уточните у организаторов
> хакатона, допустимо ли это для тестовых видео (в README шаблона разметки: «в облачные
> AI-сервисы не загружаем, не публикуем»).

## 1. Создать сервер (Droplet)

1. GitHub Student Developer Pack → DigitalOcean даёт кредит; войдите на cloud.digitalocean.com.
2. **Create → Droplets**:
   - Region: **Frankfurt** (ближе всего к Казахстану из доступных);
   - Image: **Ubuntu 24.04 (LTS) x64**;
   - Size: **Basic → Regular, 2 GB RAM / 1 CPU** (≈ $12/мес). 1 GB хватает впритык;
     для YOLO + torch в будущем лучше 4 GB;
   - Authentication: SSH key (надёжнее) или пароль.
3. Скопируйте IP созданного сервера.

## 2. Установить бэкенд (одна команда)

```bash
ssh root@<IP>
curl -fsSL https://raw.githubusercontent.com/yeskabyl/forte-analyzer/main/deploy/setup-server.sh | bash
```

Скрипт ставит Docker, включает firewall (открыты только 22, 80, 443) и swap, клонирует репозиторий
в `/opt/forte-analyzer`, создаёт `.env` со **случайным API-ключом** и запускает стек
`docker-compose.yml` + `docker-compose.prod.yml`. В конце печатает:

```
API:      https://<ip-с-дефисами>.sslip.io
API-ключ: <ключ>
```

Сохраните ключ — публичный `forte-secret-key-2026` из репозитория на сервере не работает.

## 3. Подключить сайт на Vercel

Vercel → проект **forte-analyzer** → Settings → Environment Variables:

| Name | Value | Environment |
|------|-------|-------------|
| `VITE_API_BASE_URL` | `https://<ip-с-дефисами>.sslip.io` | Production |

Затем Deployments → последний деплой → **Redeploy**. Без этой переменной сайт по-прежнему
обращается к `http://localhost:8000` (локальный режим).

## Обслуживание

```bash
cd /opt/forte-analyzer
# обновить код после git push и перезапустить
bash deploy/setup-server.sh
# логи
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker
# остановить
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Настройки — в `/opt/forte-analyzer/.env`: `API_KEY`, `DOMAIN`, `CORS_ORIGINS` (с каких сайтов
разрешены запросы), `MAX_UPLOAD_MB`. После изменения — `bash deploy/setup-server.sh`.

Чтобы не платить, когда сервер не нужен, Droplet можно удалить (Destroy) — с
выключенного сервера DigitalOcean продолжает брать деньги.
