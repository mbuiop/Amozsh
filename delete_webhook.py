import telebot

TOKEN = "7956758689:AAH3JZ3kzBybVqPwRZ_pXlyA7Pez0n3BZ0o"
bot = telebot.TeleBot(TOKEN)

bot.delete_webhook()
print("✅ وب‌هوک پاک شد")
