FROM nginx:1.25-alpine

COPY frontend/ /usr/share/nginx/html/
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
