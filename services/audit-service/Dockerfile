FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --production

COPY src/ ./src/
RUN mkdir -p /app/data

EXPOSE 3006

CMD ["npm", "start"]
