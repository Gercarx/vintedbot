import selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import telegram
import asyncio
import random
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from selenium.common.exceptions import TimeoutException

# TOKEN TELEGRAM
TELEGRAM_TOKEN = "yourtoken"

# Variabile globale per gestire lo stato del bot (continuare o fermarsi)
bot_attivo = True

# Funzione per rimuovere caratteri non validi
def rimuovi_caratteri_non_validi(testo):
    return re.sub(r'[\ud800-\udfff]', '', testo)

# Funzione per inviare articoli a Telegram
async def invia_dati_telegram(context: CallbackContext, chat_id, testo, prezzo, link, image_url):
    testo = rimuovi_caratteri_non_validi(testo)
    prezzo = rimuovi_caratteri_non_validi(prezzo)
    
    messaggio = f"📦 Nuovo articolo trovato!\n\n"
    messaggio += f"Nome: {testo}\n"
    messaggio += f"Prezzo: {prezzo}\n"
    messaggio += f"Link: {link}\n"
    
    await context.bot.send_message(chat_id=chat_id, text=messaggio)
    if image_url:
        await context.bot.send_photo(chat_id=chat_id, photo=image_url)

# Funzione per fermare il bot
async def stop(update: Update, context: CallbackContext) -> None:
    global bot_attivo
    bot_attivo = False
    if update.message:  # Verifica che update.message sia presente
        await update.message.reply_text("⛔ Il bot è stato fermato.")
    else:
        await update.callback_query.answer("⛔ Il bot è stato fermato.")  # Per i callback da pulsanti

# Messaggio di benvenuto con pulsanti interattivi
async def start(update: Update, context: CallbackContext) -> None:
    """Invia un messaggio di benvenuto con pulsanti interattivi."""
    keyboard = [
        [InlineKeyboardButton("🔍 Cerca un articolo", callback_data="cerca")],
        [InlineKeyboardButton("⛔ Stop Bot", callback_data="stop")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:  # Verifica che update.message sia presente
        await update.message.reply_text(
            "👋 Benvenuto in *VintedBot*! \n\n"
            "🔎 Per cercare un articolo, premi il pulsante *Cerca un articolo*.\n"
            "❌ Per fermare il bot, premi *Stop Bot*. ",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif update.callback_query:  # Se l'aggiornamento è un callback (pulsante)
        await update.callback_query.answer()  # Rispondi al callback per evitare blocchi

# Gestione pulsanti
async def button(update: Update, context: CallbackContext) -> None:
    """Gestisce la pressione dei pulsanti."""
    query = update.callback_query
    await query.answer()

    if query.data == "cerca":
        await query.message.reply_text("Per cercare un articolo, usa il comando:\n\n`/cerca <nome_articolo>`", parse_mode="Markdown")
    elif query.data == "stop":
        await stop(update, context)

# Funzione per creare l'URL di Vinted
def create_vinted_url(nome_articolo):
    url = f"https://www.vinted.it/catalog?new_with_tags=true&price_from=1&price_to=10&search_text={nome_articolo}"
    return url

# Funzione per mostrare il pulsante "Stop Bot"
async def mostra_pulsante_stop(chat_id, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("⛔ Stop Bot", callback_data="stop")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Vuoi fermare il bot?",
        reply_markup=reply_markup
    )

# Funzione per cercare articoli
async def cerca(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ Inserisci un articolo da cercare con `/cerca <nome_articolo>`", parse_mode="Markdown")
        return
    
    articolo = " ".join(context.args)
    url_vinted = create_vinted_url(articolo)  # Crea l'URL con il nome dell'articolo
    await update.message.reply_text(f"🔎 Sto cercando '{articolo}' su Vinted...")

    chrome_options = Options()
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--headless')  # Esegui Chrome in background
    chrome_options.add_argument('--disable-gpu')  # Disabilita la GPU per evitare errori

    service = Service("path_chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(url_vinted)
    await asyncio.sleep(3)

    # Accetta i cookie
    try:
        cookie_button = driver.find_element(By.XPATH, '//*[@id="onetrust-accept-btn-handler"]')
        cookie_button.click()
    except:
        pass 

    # Non reinserire la parola nella barra di ricerca, usa direttamente l'URL
    await asyncio.sleep(7)

    articoli_inviati_set = set()
    articoli_inviati = 0

    while bot_attivo:  # Loop continuo per cercare articoli
        if not bot_attivo:  # Controlla se il bot è stato fermato
            await update.message.reply_text("⛔ Il bot è stato fermato.")
            driver.quit()
            return

        try:
            driver.execute_script("window.scrollBy(0, 1000);")
            await asyncio.sleep(5)

            elementi_testo = driver.find_elements(By.XPATH, '//p[contains(@class, "web_ui__Text__text") and contains(@class, "web_ui__Text__caption") and contains(@class, "web_ui__Text__left") and contains(@class, "web_ui__Text__truncated")]')
            elementi_prezzo = driver.find_elements(By.XPATH, '//p[contains(@class, "web_ui__Text__text") and contains(@class, "web_ui__Text__caption") and contains(@class, "web_ui__Text__left") and contains(@class, "web_ui__Text__muted")]')
            elementi_link = driver.find_elements(By.CSS_SELECTOR, "a.new-item-box__overlay--clickable")

            if elementi_testo and elementi_prezzo and elementi_link:
                for i in range(min(len(elementi_testo), len(elementi_prezzo), len(elementi_link))):
                    if articoli_inviati >= 4:
                        break  

                    testo = elementi_testo[i].text
                    prezzo = elementi_prezzo[i].text
                    link = elementi_link[i].get_attribute("href")

                    if link in articoli_inviati_set:
                        continue

                    try:
                        image_element = driver.find_element(By.XPATH, f"//a[@href='{link}']/following-sibling::div//img")
                        image_url = image_element.get_attribute("src")
                    except:
                        image_url = None

                    await invia_dati_telegram(context, update.message.chat_id, testo, prezzo, link, image_url)
                    articoli_inviati += 1  
                    articoli_inviati_set.add(link)

            else:
                await update.message.reply_text("⚠️ Nessun nuovo articolo trovato. Riprovo...")

            if articoli_inviati < 4:
                attesa = random.randint(10, 15)
                await update.message.reply_text(f"🔄 Prossimo aggiornamento tra {attesa} secondi...")
                await asyncio.sleep(attesa)

        except TimeoutException:
            await update.message.reply_text("❌ Timeout durante la navigazione. Riprovo...")
            driver.quit()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(url_vinted)
            await asyncio.sleep(3)

        except Exception as e:
            await update.message.reply_text(f"⚠️ Errore: {str(e)}")
            await asyncio.sleep(10)

        # Mostra il pulsante "Stop Bot" alla fine di ogni ciclo
        await mostra_pulsante_stop(update.message.chat_id, context)

        articoli_inviati = 0  
        articoli_inviati_set.clear()
        await asyncio.sleep(300)  # Aspetta 5 minuti

    driver.quit()

# Funzione per avviare il bot
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cerca", cerca))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
