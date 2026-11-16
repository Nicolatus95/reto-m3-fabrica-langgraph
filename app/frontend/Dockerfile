FROM node:22 AS construccion
WORKDIR /web
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=construccion /web/dist /usr/share/nginx/html
EXPOSE 80
