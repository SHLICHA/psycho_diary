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

celery -A core worker --loglevel=info - запуск celery
sudo systemctl start redis-server - если redis не запущен

git add .
git commit -m 'Название'
git push origin master #загрузить в GitHub
git pull origin master #обновить из GitHub

python -m pytest tests/test_messages.py -v