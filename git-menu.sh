#!/bin/bash
while true; do
    clear
    echo "╔══════════════════════════════════════════╗"
    echo "║         🔧 GIT МЕНЮ                      ║"
    echo "╠══════════════════════════════════════════╣"
    echo "║  1. 📤 Залить изменения                  ║"
    echo "║  2. 📥 Скачать изменения                 ║"
    echo "║  3. 📋 Статус                            ║"
    echo "║  4. 📝 История коммитов                  ║"
    echo "║  5. 🚀 Выпустить релиз (версия+changelog)║"
    echo "║  0. ❌ Выход                             ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    read -p "Выбор: " choice

    case $choice in
        1)
            cd /opt/SLV_Bot
            read -p "Комментарий: " msg
            git add -A
            git commit -m "$msg"
            git push
            echo "✅ Отправлено!"; read -p "Enter..."
            ;;
        2)
            cd /opt/SLV_Bot
            git pull
            echo "✅ Скачано!"; read -p "Enter..."
            ;;
        3)
            cd /opt/SLV_Bot
            git status
            read -p "Enter..."
            ;;
        4)
            cd /opt/SLV_Bot
            git log --oneline -10
            read -p "Enter..."
            ;;
        5)
            cd /opt/SLV_Bot
            read -p "Новая версия (например 1.2.0): " ver
            read -p "Что изменилось (кратко): " changes
            echo "$ver" > version.txt
            today=$(date '+%d.%m.%Y')
            sed -i "4i ## v$ver ($today)\n- $changes\n" CHANGELOG.md
            
            # Обновляем BOT_VERSION в handlers.py
            sed -i 's/BOT_VERSION = "v[^"]*"/BOT_VERSION = "v$ver"/' handlers.py
            echo "✅ BOT_VERSION обновлён до v$ver"
            
            git add -A
            git commit -m "v$ver - $changes"
            git tag -a "v$ver" -m "v$ver - $changes"
            git push && git push --tags
            
            # Создаём GitHub Release
            echo "📦 Создаю GitHub Release..."
            TOKEN=$(git remote get-url origin | sed 's|.*://||; s|@github.com.*||; s|.*:||')
            curl -s -X POST https://api.github.com/repos/elifecomp/slk-telegram-bot/releases \
                -H "Authorization: token $TOKEN" \
                -H "Accept: application/vnd.github.v3+json" \
                -d "{\"tag_name\":\"v$ver\",\"name\":\"v$ver\",\"body\":\"$changes\",\"draft\":false,\"prerelease\":false}" > /dev/null
            echo "✅  GitHub Release создан!"
            systemctl restart SLV-bot
            echo "✅ Релиз v$ver выпущен!"
            read -p "Enter..."
            ;;
        0) echo "👋 Выход"; exit 0 ;;
        *) echo "Неверно"; sleep 1 ;;
    esac
done
