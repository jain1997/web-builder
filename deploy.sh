#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Agentic Web IDE — One-command deploy script
#  Usage:
#    ./deploy.sh              # Docker Compose (recommended)
#    ./deploy.sh local        # Local dev without Docker
#    ./deploy.sh stop         # Stop all containers
#    ./deploy.sh logs         # Tail container logs
#    ./deploy.sh clean        # Stop + remove volumes
# ─────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

banner() {
  echo ""
  echo -e "${PURPLE}${BOLD}"
  echo "    ╔═══════════════════════════════════════╗"
  echo "    ║         Agentic Web IDE               ║"
  echo "    ║     AI-Powered Code Generation         ║"
  echo "    ╚═══════════════════════════════════════╝"
  echo -e "${NC}"
}

info()    { echo -e "  ${BLUE}▸${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${YELLOW}!${NC} $1"; }
error()   { echo -e "  ${RED}✕${NC} $1"; }
header()  { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

# ─────────────────────────────────────────────────────────────
#  Check prerequisites
# ─────────────────────────────────────────────────────────────
check_docker() {
  if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Install it from https://docs.docker.com/get-docker/"
    exit 1
  fi
  if ! docker info &>/dev/null; then
    error "Docker daemon is not running. Start Docker Desktop and try again."
    exit 1
  fi
  success "Docker is available"
}

check_env() {
  local env_file="backend/.env"
  if [ ! -f "$env_file" ]; then
    warn "No backend/.env file found — creating from template"
    cp backend/.env.example "$env_file"
    echo ""
    error "Please set your OPENAI_API_KEY in ${BOLD}backend/.env${NC} and re-run this script."
    exit 1
  fi

  if grep -q "sk-your-key-here" "$env_file" 2>/dev/null; then
    error "OPENAI_API_KEY is still the placeholder value in backend/.env"
    error "Set a real API key and re-run this script."
    exit 1
  fi

  success "Environment file configured"
}

# ─────────────────────────────────────────────────────────────
#  Docker Compose deployment
# ─────────────────────────────────────────────────────────────
deploy_docker() {
  banner
  header "Preflight checks"
  check_docker
  check_env

  header "Building and starting services"
  info "This may take a few minutes on first run..."
  echo ""

  docker compose up --build -d

  echo ""
  header "Waiting for services"

  # Wait for backend health
  local retries=30
  while [ $retries -gt 0 ]; do
    if curl -sf http://localhost:8000/health &>/dev/null; then
      success "Backend is healthy"
      break
    fi
    retries=$((retries - 1))
    sleep 2
  done

  if [ $retries -eq 0 ]; then
    warn "Backend health check timed out — check logs with: ./deploy.sh logs"
  fi

  # Check frontend
  retries=15
  while [ $retries -gt 0 ]; do
    if curl -sf http://localhost:3000 &>/dev/null; then
      success "Frontend is healthy"
      break
    fi
    retries=$((retries - 1))
    sleep 2
  done

  if [ $retries -eq 0 ]; then
    warn "Frontend health check timed out — check logs with: ./deploy.sh logs"
  fi

  echo ""
  echo -e "  ${GREEN}${BOLD}Agentic Web IDE is running!${NC}"
  echo ""
  echo -e "  ${BOLD}Frontend${NC}  →  ${CYAN}http://localhost:3000${NC}"
  echo -e "  ${BOLD}Backend${NC}   →  ${CYAN}http://localhost:8000${NC}"
  echo -e "  ${BOLD}API Docs${NC}  →  ${CYAN}http://localhost:8000/docs${NC}"
  echo ""
  echo -e "  ${BOLD}Commands:${NC}"
  echo -e "    ./deploy.sh logs   — View live logs"
  echo -e "    ./deploy.sh stop   — Stop all services"
  echo -e "    ./deploy.sh clean  — Stop and remove data"
  echo ""
}

# ─────────────────────────────────────────────────────────────
#  Local dev deployment (no Docker)
# ─────────────────────────────────────────────────────────────
deploy_local() {
  banner
  header "Preflight checks"
  check_env

  # Check Python
  if command -v python3 &>/dev/null; then
    PYTHON=python3
  elif command -v python &>/dev/null; then
    PYTHON=python
  else
    error "Python 3.11+ is required but not found."
    exit 1
  fi
  success "Python found: $($PYTHON --version)"

  # Check Node
  if ! command -v node &>/dev/null; then
    error "Node.js 18+ is required but not found."
    exit 1
  fi
  success "Node.js found: $(node --version)"

  # Backend setup
  header "Setting up backend"
  cd "$SCRIPT_DIR/backend"

  if [ ! -d ".venv" ]; then
    info "Creating Python virtual environment..."
    $PYTHON -m venv .venv
  fi

  source .venv/bin/activate
  info "Installing Python dependencies..."
  pip install -q -r requirements.txt
  success "Backend dependencies installed"

  # Frontend setup
  header "Setting up frontend"
  cd "$SCRIPT_DIR/frontend"

  if [ ! -d "node_modules" ]; then
    info "Installing Node.js dependencies..."
    npm ci --silent
  fi
  success "Frontend dependencies installed"

  # Start services
  header "Starting services"

  # Check if Redis is running (optional)
  if command -v redis-cli &>/dev/null && redis-cli ping &>/dev/null 2>&1; then
    success "Redis is running"
  else
    warn "Redis is not running — app will use SQLite-only mode"
  fi

  # Start backend in background
  cd "$SCRIPT_DIR/backend"
  info "Starting backend on :8000..."
  source .venv/bin/activate
  uvicorn app.api.main:app --reload --port 8000 &
  BACKEND_PID=$!

  # Start frontend in background
  cd "$SCRIPT_DIR/frontend"
  info "Starting frontend on :3000..."
  npm run dev &
  FRONTEND_PID=$!

  # Trap to kill both on exit
  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

  sleep 3
  echo ""
  echo -e "  ${GREEN}${BOLD}Agentic Web IDE is running!${NC}"
  echo ""
  echo -e "  ${BOLD}Frontend${NC}  →  ${CYAN}http://localhost:3000${NC}"
  echo -e "  ${BOLD}Backend${NC}   →  ${CYAN}http://localhost:8000${NC}"
  echo ""
  echo -e "  Press ${BOLD}Ctrl+C${NC} to stop both servers."
  echo ""

  # Wait for background processes
  wait
}

# ─────────────────────────────────────────────────────────────
#  Commands
# ─────────────────────────────────────────────────────────────
stop_services() {
  header "Stopping services"
  docker compose down
  success "All services stopped"
}

show_logs() {
  docker compose logs -f --tail=100
}

clean_all() {
  header "Stopping services and removing data"
  docker compose down -v
  success "Services stopped and volumes removed"
}

# ─────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────
case "${1:-docker}" in
  local)  deploy_local  ;;
  stop)   stop_services ;;
  logs)   show_logs     ;;
  clean)  clean_all     ;;
  docker) deploy_docker ;;
  *)
    echo "Usage: ./deploy.sh [docker|local|stop|logs|clean]"
    echo ""
    echo "  docker  — Build and run with Docker Compose (default)"
    echo "  local   — Run locally without Docker"
    echo "  stop    — Stop all Docker containers"
    echo "  logs    — Tail Docker container logs"
    echo "  clean   — Stop containers and remove volumes"
    exit 1
    ;;
esac
