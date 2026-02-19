# 🚀 Быстрый старт

Краткое руководство для запуска бота за 5 минут.

## 📦 Установка

```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Создайте конфигурацию
cp .env.example .env

# 3. Отредактируйте .env и добавьте:
#    - BOT_TOKEN (получите у @BotFather)
#    - ALLOWED_USERS (ваш Telegram ID от @userinfobot)
```

## ⚙️ Настройка .env

Минимальная конфигурация:

```env
BOT_TOKEN=123456789:AAH...
ALLOWED_USERS=123456789
```

## ▶️ Запуск

```bash
python main.py
```

## ✅ Проверка

1. Откройте бота в Telegram
2. Отправьте `/start`
3. Используйте меню для управления клиентами

## 📚 Дополнительно

- Полная документация: [README.md](README.md)
- История изменений: [CHANGELOG.md](CHANGELOG.md)
- Обновление: [UPGRADE.md](UPGRADE.md)

## 🆘 Проблемы?

Проверьте логи: `logs/bot.log`

---

**Готово! Бот работает! 🎉**
