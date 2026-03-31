#!/usr/bin/env bash
set -e

git rm --cached bot.db bot.log test_bot.db || true
rm -f bot.db bot.log test_bot.db
git add .gitignore README_QUICKSTART.md config.py
echo "Готово. Теперь сделай commit."
