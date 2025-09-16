sudo service postgresql start

docker-compose up -d --build
docker stop $(docker ps -a -q) - остановить все контейнеры Docker
docker rm $(docker ps -qa) - удалить все контейнеры
docker-compose exec web python manage.py migrate - миграции в контейнере
docker-compose exec web python manage.py createsuperuser - создание суперпользователя в контейнере
docker-compose exec web python manage.py collectstatic --no-input - сбор статики в контейнере

docker build -t shlicha/dairy_bot:v1 . - локально создать образ для dockerHub
docker login -u shlicha - залогиниться в dockerHub
docker push shlicha/dairy_bot:v1 - отправить образ на DockerHub

celery -A core worker --beat --loglevel=info - запуск celery
sudo systemctl start redis-server - если redis не запущен
docker-compose logs -f celery_worker - #запуск логов celery

git add .
git commit -m 'Название'
git push origin master #загрузить в GitHub
git pull origin master #обновить из GitHub

python -m pytest tests/test_messages.py -v

Привет. Сейчас я буду присылать тебе части кода. Пока ты просто принимаешь данные. Будем дорабатывать уже существующий код.
Есть несколько ВАЖНЫХ МОМЕНТОВ
1. Ты не делаешь ничего, пока я не попрошу
2. Не делаешь ничего сверх того, что мы обсуждаем
3. Если ты со мной не согласен, ты мне прямо об этом говоришь
4. Если тебе чего то непонятно, или нужны еще какие-то части кода, ты мне об этом сообщаешь, а не пытаешься придумать
5. Перед началом решения какой-то задачи мы ее сначала обсуждаем, чтобы синхронизировать цели и задачи

Все понятно? Я начинаю