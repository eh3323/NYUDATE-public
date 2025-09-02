# NYU Dating Copilot 部署指南

本文档说明如何将 NYU Dating Copilot 部署到生产服务器。

## 🚀 快速开始

### 1. 本地部署（推荐）

```bash
# 首次部署
./deploy-local.sh user@your-server.com

# 后续更新
./deploy-local.sh user@your-server.com --no-backup

# 预览将要同步的文件
./deploy-local.sh --dry-run
```

### 2. 服务器端部署

```bash
# 在服务器上执行
./deploy.sh

# 仅创建备份
./deploy.sh --backup-only

# 回滚到上一个版本
./deploy.sh --rollback
```

## 📋 部署前准备

### 服务器要求

- Ubuntu 18.04+ 或 CentOS 7+
- Python 3.8+
- Git
- rsync
- 至少 1GB 内存
- 至少 10GB 磁盘空间

### 服务器设置

1. **创建应用用户**：
```bash
sudo useradd -m -s /bin/bash nyudating
sudo usermod -aG sudo nyudating
```

2. **设置应用目录**：
```bash
sudo mkdir -p /var/www/nyudating
sudo chown nyudating:nyudating /var/www/nyudating
```

3. **安装依赖**：
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv git rsync nginx

# CentOS/RHEL
sudo yum install python3 python3-pip git rsync nginx
```

4. **配置 SSH 密钥认证**（推荐）。

### 配置文件

1. **复制配置模板**：
```bash
cp deploy.config.example deploy.config
```

2. **编辑配置**：
```bash
nano deploy.config
```

## 🔧 详细配置

### Systemd 服务配置

1. **复制服务文件**：
```bash
sudo cp nyudating.service /etc/systemd/system/
```

2. **修改服务文件中的路径和用户**：
```bash
sudo nano /etc/systemd/system/nyudating.service
```

3. **启用服务**：
```bash
sudo systemctl daemon-reload
sudo systemctl enable nyudating
sudo systemctl start nyudating
```

### Nginx 配置

创建 Nginx 配置文件 `/etc/nginx/sites-available/nyudating`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /var/www/nyudating/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 16M;
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/nyudating /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL 证书（Let's Encrypt）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 📝 部署脚本说明

### deploy-local.sh（本地部署脚本）

从本地推送代码到服务器并执行部署。

**选项**：
- `--dry-run`: 预览将要同步的文件
- `--no-backup`: 跳过服务器端备份
- `--backup-only`: 仅创建服务器端备份
- `--sync-only`: 仅同步文件，不重启服务

**示例**：
```bash
# 完整部署
./deploy-local.sh user@server.com

# 仅同步文件
./deploy-local.sh user@server.com --sync-only

# 创建备份
./deploy-local.sh user@server.com --backup-only
```

### deploy.sh（服务器端部署脚本）

在服务器上执行的部署脚本。

**功能**：
- 自动备份当前版本
- 拉取最新代码（Git）
- 安装/更新依赖
- 重启服务
- 健康检查
- 失败回滚

## 🔍 监控和日志

### 查看服务状态

```bash
# 查看服务状态
sudo systemctl status nyudating

# 查看日志
sudo journalctl -u nyudating -f

# 查看应用日志
tail -f /var/www/nyudating/logs/app.log
```

### 健康检查

```bash
# 检查应用是否响应
curl http://localhost:9000/

# 检查进程
ps aux | grep app.py
```

## 🔒 安全建议

1. **防火墙配置**：
```bash
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

2. **定期更新系统**：
```bash
sudo apt update && sudo apt upgrade
```

3. **备份策略**：
- 设置定期数据库备份
- 备份上传的文件
- 测试恢复流程

## 🚨 故障排除

### 常见问题

1. **端口被占用**：
```bash
sudo lsof -i :9000
sudo kill -9 <PID>
```

2. **权限问题**：
```bash
sudo chown -R nyudating:nyudating /var/www/nyudating
```

3. **依赖问题**：
```bash
cd /var/www/nyudating
source .venv/bin/activate
pip install -r requirements.txt
```

### 回滚步骤

如果部署出现问题：

```bash
# 自动回滚
./deploy.sh --rollback

# 手动回滚
sudo systemctl stop nyudating
cd /var/backups/nyudating
sudo cp -r backup_YYYYMMDD_HHMMSS /var/www/nyudating
sudo systemctl start nyudating
```

## 📞 支持

如果遇到部署问题：

1. 检查日志文件
2. 确认配置正确
3. 测试网络连接
4. 检查服务器资源

---

更新时间：$(date)