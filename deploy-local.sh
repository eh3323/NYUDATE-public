#!/bin/bash

# NYU Dating Copilot 本地部署脚本
# 使用方法: ./deploy-local.sh [服务器地址] [选项]

set -e

# 配置变量（请根据实际情况修改）
# 默认使用已配置的 SSH Host 别名（之前已为您配置 Host nyuclass 免密登录）
DEFAULT_SERVER="nyuclass"
# 服务器上的实际部署目录
REMOTE_APP_DIR="/opt/nyuclass"
LOCAL_APP_DIR="$(pwd)"
EXCLUDE_FILE=".deployignore"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# 显示帮助信息
show_help() {
    echo "NYU Dating Copilot 本地部署脚本"
    echo ""
    echo "使用方法: $0 [服务器地址] [选项]"
    echo ""
    echo "参数:"
    echo "  服务器地址        SSH 连接地址或本机 SSH Host 别名，格式: user@host 或 nyuclass"
    echo "                   默认: $DEFAULT_SERVER"
    echo ""
    echo "选项:"
    echo "  --dry-run        仅显示将要同步的文件，不实际部署"
    echo "  --no-backup      跳过服务器端备份"
    echo "  --backup-only    仅在服务器端创建备份"
    echo "  --sync-only      仅同步文件，不重启服务"
    echo "  --help           显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                    # 使用默认服务器部署"
    echo "  $0 user@myserver.com                 # 部署到指定服务器"
    echo "  $0 --dry-run                         # 预览将要同步的文件"
    echo "  $0 user@myserver.com --backup-only   # 仅创建服务器端备份"
}

# 创建部署忽略文件
create_deployignore() {
    if [ ! -f "$EXCLUDE_FILE" ]; then
        log_info "创建 .deployignore 文件..."
        cat > "$EXCLUDE_FILE" << 'EOF'
# 虚拟环境
.venv/
venv/
__pycache__/
*.pyc
*.pyo

# 日志文件
logs/
*.log

# 上传文件
uploads/
evidences/

# 数据库 (PostgreSQL使用远程连接)
# No local database files

# 开发文件
.git/
.gitignore
.DS_Store
.vscode/
.idea/

# 临时文件
tmp/
temp/
*.tmp

# 配置文件（可能包含敏感信息）
.env
config.local.py

# 测试文件
tests/
test_*.py
*_test.py

# 部署脚本本身
deploy-local.sh
EOF
        log_success "已创建 .deployignore 文件，请检查并根据需要修改"
    fi
}

# 检查本地环境
check_local_environment() {
    log_info "检查本地环境..."
    
    # 检查必要文件
    if [ ! -f "app.py" ]; then
        log_error "未找到 app.py 文件，请确认在正确的项目目录中运行"
        exit 1
    fi
    
    if [ ! -f "requirements.txt" ]; then
        log_warning "未找到 requirements.txt 文件"
    fi
    
    # 检查 rsync
    if ! command -v rsync &> /dev/null; then
        log_error "未找到 rsync 命令，请安装 rsync"
        exit 1
    fi
    
    log_success "本地环境检查完成"
}

# 测试服务器连接
test_server_connection() {
    log_info "测试服务器连接: $SERVER"
    
    # 先尝试密钥认证
    if ssh -o ConnectTimeout=10 -o BatchMode=yes "$SERVER" echo "连接成功" 2>/dev/null; then
        log_success "服务器连接测试成功（使用密钥认证）"
        return 0
    fi
    
    # 如果密钥认证失败，提示用户选择密码认证
    log_warning "SSH密钥认证失败"
    echo ""
    read -p "是否使用密码认证？(y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "将使用密码认证进行连接"
        # 测试密码认证
        if ssh -o ConnectTimeout=10 -o PasswordAuthentication=yes -o PubkeyAuthentication=no "$SERVER" echo "连接成功"; then
            log_success "服务器连接测试成功（使用密码认证）"
            # 设置全局标志使用密码认证
            USE_PASSWORD_AUTH="true"
            return 0
        else
            log_error "密码认证也失败了"
        fi
    fi
    
    log_error "无法连接到服务器: $SERVER"
    log_info "请检查:"
    log_info "  1. 服务器地址是否正确"
    log_info "  2. SSH 密钥是否配置正确"
    log_info "  3. 用户名和密码是否正确"
    log_info "  4. 网络连接是否正常"
    exit 1
}

# 同步文件到服务器
sync_files() {
    log_info "同步文件到服务器..."
    
    # 构建 rsync 命令
    RSYNC_CMD="rsync -avz --progress --delete"
    
    # 如果使用密码认证，添加SSH选项
    if [[ "$USE_PASSWORD_AUTH" == "true" ]]; then
        RSYNC_CMD="$RSYNC_CMD -e 'ssh -o PasswordAuthentication=yes -o PubkeyAuthentication=no'"
    fi
    
    # 添加排除文件
    if [ -f "$EXCLUDE_FILE" ]; then
        RSYNC_CMD="$RSYNC_CMD --exclude-from=$EXCLUDE_FILE"
    fi
    
    # 添加一些常用的排除项
    # 确保不覆盖用户上传与日志
    RSYNC_CMD="$RSYNC_CMD --exclude=.git --exclude=.venv --exclude=venv --exclude=__pycache__ --exclude=*.pyc --exclude=uploads --exclude=logs"
    
    # 如果是 dry-run 模式
    if [[ "$DRY_RUN" == "true" ]]; then
        RSYNC_CMD="$RSYNC_CMD --dry-run"
        log_info "DRY RUN 模式 - 以下文件将被同步:"
    fi
    
    # 执行同步
    eval $RSYNC_CMD "$LOCAL_APP_DIR/" "$SERVER:$REMOTE_APP_DIR/"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN 完成，没有实际文件被传输"
        exit 0
    fi
    
    log_success "文件同步完成"
}

# 在服务器上执行部署
remote_deploy() {
    if [[ "$SYNC_ONLY" == "true" ]]; then
        log_info "仅同步文件模式，跳过服务器端部署"
        return 0
    fi

    log_info "在服务器上执行依赖安装与部署/重启..."

    REMOTE_CMD='set -e; cd '"$REMOTE_APP_DIR"' && \
        if [ -f requirements.txt ]; then \
            echo "安装/更新依赖..."; \
            if [ -d venv ]; then VENV_DIR=venv; elif [ -d .venv ]; then VENV_DIR=.venv; else python3 -m venv venv && VENV_DIR=venv; fi; \
            . "$VENV_DIR"/bin/activate; \
            python -V; \
            pip install --upgrade pip; \
            pip install -r requirements.txt; \
        else \
            echo "未找到 requirements.txt，跳过依赖安装"; \
        fi; \
        if systemctl list-unit-files 2>/dev/null | grep -q "^nyuclass\\.service"; then \
            echo "检测到 systemd 服务 nyuclass，正在重启..."; \
            sudo systemctl restart nyuclass && echo "nyuclass 重启完成"; \
        elif [ -x ./deploy.sh ]; then \
            echo "未检测到 nyuclass 服务，回退执行 ./deploy.sh"; \
            ./deploy.sh '"$DEPLOY_OPTIONS"'; \
        else \
            echo "未发现 nyuclass 服务或 deploy.sh，已完成文件同步，但未执行重启"; \
        fi'

    if [[ "$USE_PASSWORD_AUTH" == "true" ]]; then
        ssh -o PasswordAuthentication=yes -o PubkeyAuthentication=no "$SERVER" "$REMOTE_CMD"
    else
        ssh "$SERVER" "$REMOTE_CMD"
    fi

    log_success "服务器端操作完成"
}

# 部署后检查
post_deploy_check() {
    if [[ "$SYNC_ONLY" == "true" ]] || [[ "$BACKUP_ONLY" == "true" ]]; then
        return 0
    fi

    log_info "执行部署后检查..."
    
    # 检查服务是否正常运行
    if [[ "$USE_PASSWORD_AUTH" == "true" ]]; then
        if ssh -o PasswordAuthentication=yes -o PubkeyAuthentication=no "$SERVER" "curl -f -s http://127.0.0.1:9000/ > /dev/null"; then
            log_success "应用运行正常"
        else
            log_warning "应用可能没有正常启动，请检查服务器日志"
        fi
    else
        if ssh "$SERVER" "curl -f -s http://127.0.0.1:9000/ > /dev/null"; then
            log_success "应用运行正常"
        else
            log_warning "应用可能没有正常启动，请检查服务器日志"
        fi
    fi
}

# 主函数
main() {
    log_info "开始本地部署流程..."
    log_info "时间: $(date)"
    
    # 解析命令行参数
    SERVER="$DEFAULT_SERVER"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --no-backup)
                NO_BACKUP="true"
                shift
                ;;
            --backup-only)
                BACKUP_ONLY="true"
                shift
                ;;
            --sync-only)
                SYNC_ONLY="true"
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            --*)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
            *)
                if [[ "$1" =~ @ ]]; then
                    SERVER="$1"
                else
                    log_error "无效的服务器地址: $1"
                    show_help
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # 执行部署步骤
    create_deployignore
    check_local_environment
    test_server_connection
    sync_files
    remote_deploy
    post_deploy_check
    
    log_success "部署流程完成！"
    
    if [[ "$DRY_RUN" != "true" ]] && [[ "$SYNC_ONLY" != "true" ]] && [[ "$BACKUP_ONLY" != "true" ]]; then
        log_info "您可以通过以下地址访问应用:"
        log_info "  http://$(echo $SERVER | cut -d'@' -f2):9000"
    fi
}

# 错误处理
trap 'log_error "部署过程中发生错误，退出码: $?"' ERR

# 运行主函数
main "$@"