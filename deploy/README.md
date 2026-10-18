# Деплой бэкенда на сервер (DigitalOcean или Azure for Students)

Бэкенд (API + Celery-воркер + Redis) работает на сервере 24/7, интерфейс остаётся на Vercel.
Подходит любой сервер с Ubuntu 22.04/24.04 — ниже два варианта создания (шаг 1a или 1b),
дальше шаги общие.
HTTPS — через Caddy с бесплатным сертификатом Let's Encrypt; свой домен не нужен,
используется `<ip-сервера>.sslip.io`.

> Видео, которые загружают на сайт, обрабатываются на этом сервере. Уточните у организаторов
> хакатона, допустимо ли это для тестовых видео (в README шаблона разметки: «в облачные
> AI-сервисы не загружаем, не публикуем»).

## 1a. Сервер в DigitalOcean (Droplet)

1. GitHub Student Developer Pack → DigitalOcean даёт кредит; войдите на cloud.digitalocean.com.
2. **Create → Droplets**:
   - Region: **Frankfurt** (ближе всего к Казахстану из доступных);
   - Image: **Ubuntu 24.04 (LTS) x64**;
   - Size: **Basic → Regular, 2 GB RAM / 1 CPU** (≈ $12/мес). 1 GB хватает впритык;
     для YOLO + torch в будущем лучше 4 GB;
   - Authentication: SSH key (надёжнее) или пароль.
3. Скопируйте IP созданного сервера.
4. Поле «Select a project» — это папка для ресурсов в панели DigitalOcean, с репозиторием
   не связано; можно оставить проект по умолчанию.

## 1b. Сервер в Azure for Students

$100 кредита на 12 месяцев без банковской карты; когда кредит закончится, ресурсы
остановятся, а не выставят счёт. VM размера B1s входит в бесплатные услуги на год (750 ч/мес).

1. Активируйте подписку на azure.microsoft.com/free/students (вход через университетскую почту).
2. Портал Azure → **Virtual machines → Create → Azure virtual machine**:
   - Resource group: новая, например `forte-analyzer`;
   - Region: ближайший разрешённый (Germany West Central, Poland Central, North Europe).
     Студенческая подписка разрешает не все регионы: при ошибке «disallowed by policy»
     выберите другой;
   - Image: **Ubuntu Server 24.04 LTS - x64 Gen2**;
   - Size: **B1s** (1 GiB, бесплатно) — хватает для демо, скрипт добавит swap. Если медленно
     или нужен YOLO + torch — потом VM → Size → **B2s** (4 GiB, ≈ $35/мес из кредита);
   - Authentication: **SSH public key**, username `azureuser` — Azure предложит скачать `.pem`;
   - Inbound ports: отметьте **SSH (22), HTTP (80), HTTPS (443)**. Без 80/443 Let's Encrypt
     не выдаст сертификат. Если забыли: VM → Networking → Add inbound port rule.
3. **Review + create**, затем скопируйте Public IP address со страницы VM.

## 2. Установить бэкенд (одна команда)

DigitalOcean (вход под root):

```bash
ssh root@<IP>
curl -fsSL https://raw.githubusercontent.com/yeskabyl/forte-analyzer/main/deploy/setup-server.sh | bash
```

Azure (вход под `azureuser`, поэтому `sudo`):

```bash
ssh -i путь/к/ключу.pem azureuser@<IP>
curl -fsSL https://raw.githubusercontent.com/yeskabyl/forte-analyzer/main/deploy/setup-server.sh | sudo bash
```

На Windows, если ssh ругается на права `.pem` («UNPROTECTED PRIVATE KEY FILE»), положите
ключ в `C:\Users\<вы>\.ssh\` — туда у других пользователей доступа нет.

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
# обновить код после git push и перезапустить (на Azure: sudo bash ...)
bash deploy/setup-server.sh
# логи
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker
# остановить
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Настройки — в `/opt/forte-analyzer/.env`: `API_KEY`, `DOMAIN`, `CORS_ORIGINS` (с каких сайтов
разрешены запросы), `MAX_UPLOAD_MB`. После изменения — `bash deploy/setup-server.sh`.

Чтобы не тратить деньги, когда сервер не нужен:

- **DigitalOcean** — только удалить Droplet (Destroy): за выключенный сервер деньги списываются.
- **Azure** — VM → **Stop**: машина освобождается (deallocated), вычисления не оплачиваются,
  остаются копейки за диск. После Start IP может смениться — тогда снова запустите
  `sudo bash deploy/setup-server.sh` после правки `DOMAIN` в `.env` (или удалите `.env`,
  скрипт создаст новый, но с новым API-ключом) и обновите `VITE_API_BASE_URL` в Vercel.
  Чтобы IP не менялся: Public IP address → Configuration → Assignment: **Static**.
