# TLS certificates for nginx

Положите сюда на сервере (не коммитьте):

- `fullchain.pem` — сертификат + цепочка
- `privkey.pem` — приватный ключ

В контейнере они монтируются как `/etc/nginx/certs/` (readonly).

После появления файлов:

```bash
docker compose up -d nginx
```
