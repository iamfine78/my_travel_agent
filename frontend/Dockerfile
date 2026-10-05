# ============================================
# 前端镜像：Vite 构建 → nginx 托管
# 高德 Key 来源：Vite 在「构建期」把 frontend/.env 里的 VITE_* 内联进产物，
#   所以构建上下文必须带上 frontend/.env（见 .dockerignore 的说明）。
#   这与开发时用的是同一个文件，无需重复配置。
# 注意：产物里会含该 Key（浏览器端无法真正保密），因此不要把这套构建产物
#   推到公共镜像仓库；Key 的防护靠高德控制台的域名白名单 + 定期轮换。
# ============================================
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---------- 运行阶段：只带构建产物 ----------
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
