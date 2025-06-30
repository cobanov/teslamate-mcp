#!/bin/bash

# TeslaMate MCP Deployment Script
# This script helps manage the Docker deployment of TeslaMate MCP

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Docker and Docker Compose are installed
check_requirements() {
    print_status "Checking requirements..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_status "All requirements satisfied."
}

# Setup environment
setup_env() {
    if [ ! -f .env ]; then
        if [ -f env.example ]; then
            print_status "Creating .env file from env.example..."
            cp env.example .env
            print_warning "Please edit .env file with your database credentials before starting the service."
            echo "Press Enter to continue after editing .env file..."
            read
        else
            print_error "No env.example file found. Please create .env file manually."
            exit 1
        fi
    else
        print_status ".env file already exists."
    fi
}

# Build the Docker image
build() {
    print_status "Building Docker image..."
    docker-compose build
}

# Start the service
start() {
    print_status "Starting TeslaMate MCP service..."
    docker-compose up -d
    
    # Wait for service to be ready
    print_status "Waiting for service to be ready..."
    sleep 5
    
    # Check if service is running
    if docker-compose ps | grep -q "Up"; then
        print_status "Service is running!"
        print_status "MCP server is available at:"
        print_status "  - Endpoint: http://localhost:8888/mcp"
        
        # Check if authentication is enabled
        if [ -f .env ]; then
            source .env
            if [ ! -z "$AUTH_TOKEN" ]; then
                print_status "  - Auth required: Bearer token configured"
                print_status "  - Use header: Authorization: Bearer $AUTH_TOKEN"
            fi
        fi
    else
        print_error "Service failed to start. Check logs with: docker-compose logs"
        exit 1
    fi
}

# Stop the service
stop() {
    print_status "Stopping TeslaMate MCP service..."
    docker-compose down
}

# View logs
logs() {
    docker-compose logs -f teslamate-mcp
}

# Update the service
update() {
    print_status "Updating TeslaMate MCP..."
    git pull
    build
    print_status "Restarting service..."
    docker-compose down
    docker-compose up -d
}

# Test database connection
test_db() {
    print_status "Testing database connection..."
    docker-compose exec teslamate-mcp python -c "
import os
import psycopg
try:
    conn = psycopg.connect(os.getenv('DATABASE_URL'))
    print('✓ Database connection successful!')
    conn.close()
    
    # Check authentication status
    auth_token = os.getenv('AUTH_TOKEN')
    if auth_token:
        print(f'✓ Bearer token authentication enabled')
        print(f'  Authorization header: Bearer {auth_token}')
    else:
        print('⚠ Bearer token authentication not configured')
except Exception as e:
    print('✗ Database connection failed:', str(e))
"
}

# Show status
status() {
    print_status "Service status:"
    docker-compose ps
}

# Main menu
show_menu() {
    echo ""
    echo "TeslaMate MCP Deployment Manager"
    echo "================================"
    echo "1. Setup environment"
    echo "2. Build image"
    echo "3. Start service"
    echo "4. Stop service"
    echo "5. View logs"
    echo "6. Update service"
    echo "7. Test database connection"
    echo "8. Show status"
    echo "9. Full deploy (setup + build + start)"
    echo "0. Exit"
    echo ""
}

# Full deployment
full_deploy() {
    check_requirements
    setup_env
    build
    start
    test_db
}

# Handle command line arguments
if [ $# -eq 0 ]; then
    # Interactive mode
    while true; do
        show_menu
        read -p "Enter your choice: " choice
        
        case $choice in
            1) setup_env ;;
            2) build ;;
            3) start ;;
            4) stop ;;
            5) logs ;;
            6) update ;;
            7) test_db ;;
            8) status ;;
            9) full_deploy ;;
            0) print_status "Goodbye!"; exit 0 ;;
            *) print_error "Invalid choice. Please try again." ;;
        esac
        
        if [ "$choice" != "5" ]; then
            echo ""
            read -p "Press Enter to continue..."
        fi
    done
else
    # Command mode
    case $1 in
        setup) setup_env ;;
        build) build ;;
        start) start ;;
        stop) stop ;;
        logs) logs ;;
        update) update ;;
        test) test_db ;;
        status) status ;;
        deploy) full_deploy ;;
        *) 
            print_error "Unknown command: $1"
            echo "Usage: $0 [setup|build|start|stop|logs|update|test|status|deploy]"
            exit 1
            ;;
    esac
fi 