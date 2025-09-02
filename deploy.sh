#!/bin/bash

# NYU Dating Copilot 部署脚本
# 使用方法: ./deploy.sh [选项]
# 选项:
#   --backup-only     只创建备份，不部署
#   --no-backup      跳过备份步骤
#   --no-restart     部署后不重启服务
#   --rollback       回滚到上一个备份版本

set -e  # 遇到错误立即退出

# 配置变量
APP_NAME="nyudating"
APP_DIR="/var/www/nyudating"  # 修改为您的服务器路径
BACKUP_DIR="/var/backups/nyudating"
SERVICE_NAME="nyudating"  # systemd 服务名，如果使用的话
PORT=9000
HEALTH_CHECK_URL="http://localhost:$PORT/"
BACKUP_KEEP=5  # 保留的备份数量

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为 root 用户
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "正在以 root 用户运行部署脚本"
    fi
}

# 创建必要的目录
setup_directories() {
    log_info "创建必要的目录..."
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$APP_DIR"
    
    # 在应用目录中创建必要的子目录
    if [ -d "$APP_DIR" ]; then
        cd "$APP_DIR"
        mkdir -p logs uploads static evidences
        # 设置适当的权限
        chmod 755 logs uploads static evidences 2>/dev/null || true
    fi
}

# 备份当前版本
backup_current() {
    if [[ "$NO_BACKUP" == "true" ]]; then
        log_info "跳过备份步骤"
        return 0
    fi

    log_info "创建当前版本备份..."
    
    if [ ! -d "$APP_DIR" ]; then
        log_warning "应用目录不存在，跳过备份"
        return 0
    fi

    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"
    
    # 停止服务（如果正在运行）
    stop_service
    
    # 创建备份
    cp -r "$APP_DIR" "$BACKUP_PATH"
    log_success "备份创建完成: $BACKUP_PATH"
    
    # 清理旧备份
    cleanup_old_backups
    
    # 如果只是备份，则退出
    if [[ "$BACKUP_ONLY" == "true" ]]; then
        log_success "仅备份模式，完成"
        exit 0
    fi
}

# 清理旧备份
cleanup_old_backups() {
    log_info "清理旧备份文件..."
    cd "$BACKUP_DIR"
    ls -t backup_* 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) | xargs -r rm -rf
}

# 停止服务
stop_service() {
    log_info "停止服务..."
    
    # 尝试使用 systemd
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        sudo systemctl stop "$SERVICE_NAME"
        log_info "已停止 systemd 服务: $SERVICE_NAME"
        return 0
    fi
    
    # 尝试通过端口杀死进程
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_info "通过端口 $PORT 停止进程..."
        lsof -ti:$PORT | xargs kill -TERM 2>/dev/null || true
        sleep 3
        lsof -ti:$PORT | xargs kill -KILL 2>/dev/null || true
    fi
    
    # 尝试通过进程名停止
    pkill -f "python.*app.py" 2>/dev/null || true
}

# 更新代码
update_code() {
    log_info "更新应用代码..."
    
    cd "$APP_DIR"
    
    # 如果是 Git 仓库，则拉取最新代码
    if [ -d ".git" ]; then
        log_info "拉取最新代码..."
        git fetch origin
        git pull origin main  # 或者您的主分支名
        log_success "代码更新完成"
    else
        # 检查是否有 app.py 文件，说明代码已经存在
        if [ -f "app.py" ]; then
            log_info "检测到应用文件，假设代码已通过其他方式更新"
            log_success "跳过代码更新步骤"
        else
            log_warning "不是 Git 仓库且未找到应用文件"
            log_info "请确保代码已上传到 $APP_DIR"
            log_info "您可以使用 rsync 或 scp 上传代码："
            log_info "  rsync -av --exclude='.venv' --exclude='uploads' /本地/项目/路径/ user@server:$APP_DIR/"
            read -p "代码已更新？按 Enter 继续..."
        fi
    fi
}

# 安装/更新依赖
install_dependencies() {
    log_info "安装/更新依赖..."
    
    cd "$APP_DIR"
    
    # 创建虚拟环境（如果不存在）
    if [ ! -d ".venv" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv .venv
    fi
    
    # 激活虚拟环境并安装依赖
    source .venv/bin/activate
    
    if [ -f "requirements.txt" ]; then
        log_info "安装 Python 依赖..."
        pip install --upgrade pip
        pip install -r requirements.txt
        log_success "依赖安装完成"
    else
        log_warning "未找到 requirements.txt 文件"
    fi
}

# 安装并启动 Redis（Ubuntu/Debian 优先），其他发行版给出提示
ensure_redis() {
    log_info "检查并安装 Redis..."

    if command -v redis-server >/dev/null 2>&1; then
        log_info "已检测到 redis-server"
    else
        if command -v apt-get >/dev/null 2>&1; then
            log_info "使用 apt-get 安装 redis-server"
            sudo apt-get update -y
            sudo apt-get install -y redis-server
        elif command -v yum >/dev/null 2>&1; then
            log_info "使用 yum 安装 redis（软件包名可能为 redis）"
            sudo yum install -y redis || true
        elif command -v dnf >/dev/null 2>&1; then
            log_info "使用 dnf 安装 redis（软件包名可能为 redis）"
            sudo dnf install -y redis || true
        else
            log_warning "未识别的包管理器，请手动安装 Redis"
        fi
    fi

    # 尝试启动并设置开机自启
    if systemctl list-unit-files 2>/dev/null | grep -q "^redis-server\.service\|^redis\.service"; then
        if systemctl list-unit-files | grep -q "^redis-server\.service"; then
            sudo systemctl enable --now redis-server || sudo systemctl restart redis-server || true
        else
            sudo systemctl enable --now redis || sudo systemctl restart redis || true
        fi
        log_success "Redis 服务已启用并启动"
    else
        # 某些发行版安装后服务名不同，做一次尝试
        sudo systemctl enable --now redis-server 2>/dev/null || sudo systemctl enable --now redis 2>/dev/null || true
        log_info "如果 Redis 未成功启动，请检查系统服务名（redis/redis-server）"
    fi
}

# 为应用配置 Redis 的存储 URI 到 .env（若未配置）
configure_redis_env() {
    cd "$APP_DIR"
    if [ ! -f .env ]; then
        log_info "创建 .env 并写入 Redis 配置"
        echo "RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0" >> .env
        log_success ".env 已创建并写入 RATELIMIT_STORAGE_URI"
    else
        if grep -q "^RATELIMIT_STORAGE_URI=" .env; then
            log_info ".env 已包含 RATELIMIT_STORAGE_URI，保持不变"
        else
            log_info "向现有 .env 追加 RATELIMIT_STORAGE_URI"
            echo "RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0" >> .env
            log_success "已向 .env 追加 RATELIMIT_STORAGE_URI"
        fi
    fi
}

# 数据库迁移
migrate_database() {
    log_info "检查数据库迁移..."
    
    cd "$APP_DIR"
    source .venv/bin/activate
    
    # 如果有迁移脚本，在这里执行
    # python migrate.py
    # 或者
    # flask db upgrade
    
    log_info "数据库检查完成"
}

# 启动服务
start_service() {
    if [[ "$NO_RESTART" == "true" ]]; then
        log_info "跳过服务启动"
        return 0
    fi

    log_info "启动服务..."
    
    cd "$APP_DIR"
    
    # 创建必要的目录
    mkdir -p logs uploads static
    
    # 尝试使用 systemd
    if systemctl list-unit-files | grep -q "$SERVICE_NAME.service"; then
        sudo systemctl start "$SERVICE_NAME"
        sudo systemctl enable "$SERVICE_NAME"
        log_success "已启动 systemd 服务: $SERVICE_NAME"
        return 0
    fi
    
    # 使用 nohup 在后台启动
    log_info "使用 nohup 启动应用..."
    source .venv/bin/activate
    nohup python app.py > logs/app.log 2>&1 &
    
    # 等待服务启动
    sleep 5
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    for i in {1..30}; do
        if curl -f -s "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
            log_success "应用启动成功，健康检查通过"
            return 0
        fi
        log_info "等待应用启动... ($i/30)"
        sleep 2
    done
    
    log_error "健康检查失败，应用可能没有正常启动"
    return 1
}

# 回滚到上一个版本
rollback() {
    log_info "回滚到上一个备份版本..."
    
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_* 2>/dev/null | head -n 1)
    
    if [ -z "$LATEST_BACKUP" ]; then
        log_error "没有找到备份文件"
        exit 1
    fi
    
    log_info "回滚到: $LATEST_BACKUP"
    
    # 停止当前服务
    stop_service
    
    # 删除当前版本并恢复备份
    rm -rf "$APP_DIR"
    cp -r "$LATEST_BACKUP" "$APP_DIR"
    
    # 启动服务
    start_service
    
    # 健康检查
    if health_check; then
        log_success "回滚成功"
    else
        log_error "回滚后健康检查失败"
        exit 1
    fi
}

# 显示帮助信息
show_help() {
    echo "NYU Dating Copilot 部署脚本"
    echo ""
    echo "使用方法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --backup-only     只创建备份，不部署"
    echo "  --no-backup      跳过备份步骤"
    echo "  --no-restart     部署后不重启服务"
    echo "  --rollback       回滚到上一个备份版本"
    echo "  --help           显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                    # 完整部署（备份 + 更新 + 重启）"
    echo "  $0 --backup-only      # 只创建备份"
    echo "  $0 --no-backup        # 不创建备份直接部署"
    echo "  $0 --rollback         # 回滚到上一个版本"
}

# 主函数
main() {
    log_info "开始部署 NYU Dating Copilot..."
    log_info "时间: $(date)"
    
    # 检查权限
    check_root
    
    # 创建目录
    setup_directories
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backup-only)
                BACKUP_ONLY="true"
                shift
                ;;
            --no-backup)
                NO_BACKUP="true"
                shift
                ;;
            --no-restart)
                NO_RESTART="true"
                shift
                ;;
            --rollback)
                rollback
                exit 0
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 执行部署步骤
    backup_current
    update_code
    ensure_redis
    install_dependencies
    configure_redis_env
    migrate_database
    start_service
    
    # 健康检查
    if health_check; then
        log_success "部署成功完成！"
        log_info "应用地址: $HEALTH_CHECK_URL"
    else
        log_error "部署完成但健康检查失败"
        log_warning "您可以使用 --rollback 选项回滚到上一个版本"
        exit 1
    fi
}

# 错误处理
trap 'log_error "部署过程中发生错误，退出码: $?"' ERR

# 运行主函数
main "$@"