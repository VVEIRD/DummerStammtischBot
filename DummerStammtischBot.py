# -*- coding: utf-8 -*-
## Stammtischbot
#
# Macht Mittwochs eine Umfrage um herauszufinden wohin es zum Stammtisch gehen soll

import sys
import json
import sqlite3
from telegram.ext import Updater
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters
import datetime, time
import os
import logging
from threading import Thread
import sys

TOKEN = sys.argv[1]

DEFAULT_STAMMTISCHTAG = 3

MAX_LOCATIONS = 30

TAGE = {1 : "Montag", 2 : "Dienstag", 3 : "Mittwoch", 4 : "Donnerstag", 5 : "Freitag", 6 : "Samstag", 7 : "Sonntag"}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

conn = sqlite3.connect('DummerStammtischBot.db')

c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS chatrooms
             (chat_id integer,
                stammtischtag integer,
                last_notified integer,
                last_voting_notification integer
              )''')

c.execute('''CREATE TABLE IF NOT EXISTS "locations" (
    "chat_id"    INTEGER,
    "l_id"    INTEGER,
    "location"    TEXT UNIQUE,
    PRIMARY KEY("chat_id","l_id")
)''')

c.execute('''CREATE TABLE IF NOT EXISTS "votings" (
    "chat_id"    INTEGER,
    "member_id"    INTEGER,
    "member_name"    TEXT,
    "location_id"    INTEGER,
    PRIMARY KEY("chat_id","member_id")
)''')

######
## Liste mit den Locations fuer den Stammtisch
######

def load_locations():
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    locations = {}
    for row in c.execute('SELECT chat_id, l_id, location FROM locations'):
        if row[0] not in locations:
            locations[row[0]] = []
        locations[row[0]].append((row[1], row[2]))
    conn.close()
    return locations

# Lade Locations wenn die Datei fuer locations existiert

locations = load_locations()


# Wenn keine Location existiert, erzeuge eine leere Liste

if locations == None:
    locations = {}


######
## Liste mit den Chats die der Bot angehoert
######

def load_chatrooms():
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    chatrooms = {}
    for row in c.execute('SELECT chat_id, stammtischtag, last_notified, last_voting_notification FROM chatrooms'):
        chatrooms[row[0]] = [row[1],row[2], row[3]]
    conn.close()
    return chatrooms

# Lade chatrooms wenn die Datei fuer chatrooms existiert

chatrooms = load_chatrooms()

# Wenn keine Location existiert, erzeuge eine leere Liste

if chatrooms == None:
    chatrooms = {}

conn.commit()
conn.close()

######
## Methoden fuer den Chatbot
######

def execute_query(query, args):
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    c.execute(query, args)
    conn.commit()
    conn.close()

def execute_select(query, args):
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    result = []
    for row in c.execute(query, args):
        result.append(row)
    conn.close()
    return result

def add_chatroom(chat_id):
    if chat_id not in chatrooms:
        chatrooms[chat_id] = [DEFAULT_STAMMTISCHTAG, 0, 0]
        print 'New chatroom: ' + str(chat_id)
        execute_query('INSERT INTO chatrooms (chat_id, stammtischtag, last_notified, last_voting_notification) VALUES (?, ?, 0, 0)',  [chat_id, chatrooms[chat_id]])

def remove_chatroom(chat_id):
    if chat_id in chatrooms:
        print 'Removed from Chat: ' + str(chat_id)
        chatrooms.pop(chat_id, None)
        locations.pop(chat_id, None)
        execute_query('DELETE FROM chatrooms WHERE chat_id = ?', [chat_id])
        execute_query('DELETE FROM votings WHERE chat_id = ?', [chat_id])
        execute_query('DELETE FROM locations WHERE chat_id = ?', [chat_id])
        print 'Removed from chatroom: %s' % chat_id

def start(update, context):
    add_chatroom(update.message.chat.id)
    context.bot.send_message(chat_id=update.message.chat_id, text="I'm a bot, please talk to me!")

def echo(update, context):
    update.message.reply_text('Hallo %s!' % update.message.from_user.first_name)
    if hasattr(update, 'message') and hasattr(update.message, 'text') and update.message.text != None:
        message = update.message.text
        if "fuchs" in update.message.text:
            message = "der Has'"
        elif "has" in update.message.text:
            message = "Hurz!"
        elif "hurz" in update.message.text:
            message = "sehr gut!"
        context.bot.send_message(chat_id=update.message.chat_id, text=message)

def add_location(update, context):
    global locations
    add_chatroom(update.message.chat.id)
    chat_id = update.message.chat.id
    location = ' '.join(context.args).strip()
    from_user = context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    is_admin = 'administrator' == from_user.status
    is_creator = 'creator' == from_user.status
    if not is_creator and not is_admin:
        update.message.reply_text(u'Du bist kein Admin, sorry!')
        return
    if chat_id not in locations:
        locations[chat_id] = []
    if location and location not in locations[chat_id] and len(locations) <= MAX_LOCATIONS:
        execute_query('''INSERT INTO locations (chat_id, l_id, location) VALUES (?, Ifnull((SELECT max(l_id)+1 FROM locations WHERE chat_id = ?), 1), ?)''', (chat_id, chat_id, location))
        locations = load_locations()
        update.message.reply_text('Das Ziel ' + location + u' wurde hinzugefügt')
    elif len(locations) > MAX_LOCATIONS:
        update.message.reply_text('Ihr habt das Limit von %s Locations erreicht, sorry!')

def list_locations(update, context):
    message = u'Folgende Stammtischziele stehen zur Verfügung:\r\n'
    if update.message.chat.id in locations:
        i = 1
        for loc in locations[update.message.chat.id]:
            message = message + str(loc[0]) + '. ' + loc[1] + '\r\n'
            i += 1
        context.bot.send_message(chat_id=update.message.chat_id, text=message)
    else:
        context.bot.send_message(chat_id=update.message.chat_id, text=u'Es gibt noch keine Stammtischziele, füge welche mit /add hinzu')

def set_stammtischtag(update, context):
    chat_id = update.message.chat.id
    from_user = context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    is_admin = 'administrator' == from_user.status
    is_creator = 'creator' == from_user.status
    if not is_creator and not is_admin:
        update.message.reply_text(u'Du bist kein Admin, sorry!')
        return
    for arg in context.args:
        try:
            tag = int(arg)
            if chat_id in chatrooms and tag >= 1 and tag <= 7:
                chatrooms[chat_id] = tag
                execute_query('UPDATE chatrooms SET stammtischtag = ? WHERE chat_id = ?', [tag, chat_id])
                update.message.reply_text(u'Der Stammtischtag wurde auf %s gesetzt' % TAGE[tag])
            elif tag < 1 or tag > 7:
                update.message.reply_text(u'Erlaubte Werte sind 1 bis 7 für Mon bis Son')
        except ValueError:
            update.message.reply_text(u'Erlaubte Werte sind 1 bis 7 für Mon bis Son')


# Event handler wenn der Bot einem Gruppenchat hinzugefuegt wird
def new_member(update, context):
    for member in update.message.new_chat_members:
        print(member)
        if member.username == 'DummerStammtischBot':
            add_chatroom(update.message.chat.id)
            context.bot.send_message(chat_id=update.message.chat_id, text=u'Hallo zusammen, ich bin eurem Chat beigetreten\r\nFolgende Befehl stehen euch zur Auswahl:\r\n /stammtischtag oder /st: Legt den Tag des Stammtischs fest\r\n /add: Ein Stammtischziel hinzufügen\r\n /list: Alle Stammtischziele anzeigen')
        else:
            update.message.reply_text(u'Hallo ' + member.username + ', willkommen am Stammtisch!')

# Event handler wenn der Bot einem Gruppenchat entfernt wird
def left_member(update, context):
    member = update.message.left_chat_member
    print(member)
    if member.username == 'DummerStammtischBot':
        remove_chatroom(update.message.chat.id)

def help(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=u'''Ich bin der StammtischBot!\r\n
Folgende Befhele stehen euch zur Auswahl:

[Admins]
 /stammtischtag oder /st: Legt den Tag des Stammtischs fest
 /add: Ein Stammtischziel hinzufügen

[Alle]
 /list: Alle Stammtischziele anzeigen
 /help: Diese Nachricht anzeigen''')

def is_voting_time(chat_id):
    now = int(time.time())
    weekday = datetime.datetime.today().weekday()+1
    hour = datetime.datetime.now().hour
    # Am Tag vor dem Stammtisch soll abgestimmt werden
    dayToNotifyAt = chatrooms[chat_id][0]-1
    # Zeitpunkt an dem das letztre Voting gestartet wurde
    lastNotified = chatrooms[chat_id][1]
    # Zeitpunkt an dem das letztre Voting beendet wurde
    lastVotingNotified = chatrooms[chat_id][2]
    # Wir wollen am Vortag zwischen 8 und 18 Uhr voten
    return dayToNotifyAt == weekday and hour >= 8 and hour < 18

def notifier(context):
    for chat_id in chatrooms:
        now = int(time.time())
        weekday = datetime.datetime.today().weekday()+1
        hour = datetime.datetime.now().hour
        # Am Tag vor dem Stammtisch soll abgestimmt werden
        dayToNotifyAt = chatrooms[chat_id][0]-1
        # Zeitpunkt an dem das letztre Voting gestartet wurde
        lastNotified = chatrooms[chat_id][1]
        # Zeitpunkt an dem das letztre Voting beendet wurde
        lastVotingNotified = chatrooms[chat_id][2]
        # Wir wollen am Vortag installieren nur einmal pro Woche nach 8 Uhr
        if dayToNotifyAt == weekday and lastNotified+518400 < now and hour >= 8:
            print "Notifying %s" % chat_id
            execute_query('DELETE FROM votings WHERE chat_id = ?', [chat_id])
            message = u'Hallo, morgen ist wieder Stammtisch. Bitte voted bis heute um 18 Uhr, für ein Ziel.\nWenn man voted muss man kommen, sonst gibts Haue!\n\n'
            if chat_id in locations:
                message += u'Folgende Stammtischziele stehen zur Verfügung:\r\n'
                for loc in locations[chat_id]:
                    message += '%s. %s\r\n' % (loc[0],loc[1])
                message += u'\nStimme mit 1 bis %s ab' % len(locations[chat_id])
            else:
                message += u'Leider gibt es noch keine Ziele. Füge welche mit /add <Name> hinzu'

            context.bot.send_message(chat_id=chat_id, text=message)
            execute_query('UPDATE chatrooms SET last_notified = ? WHERE chat_id = ?', [now, chat_id])
            chatrooms[chat_id][1] = now
        if dayToNotifyAt == weekday and lastVotingNotified+518400 < now and hour >= 18:
            conn = sqlite3.connect('DummerStammtischBot.db')
            c = conn.cursor()
            message = 'Die Abstimmungszeit ist vorbei! Ihr habt wie folgt abgestimmt:\n\n'
            i = 1
            for row in c.execute('select (SELECT location FROm locations l WHERE l.l_id = v.location_id AND l.chat_id = v.chat_id) location, count(*) c FROM votings v WHERE chat_id = ? GROUP BY location_id ORDER BY c DESC', [chat_id]):
                message += '%s. %s (%s Stimmen)\n' % (i, row[0], row[1])
                i += 1
            organisierer = c.execute('SELECT member_name FROM votings v WHERE chat_id = ? AND member_id IN (SELECT  member_id FROM votings v2 WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1)' , [chat_id, chat_id]).fetchone()[0]
            message += '\n%s darf diese Woche den Stammtisch organisieren' % organisierer
            context.bot.send_message(chat_id=chat_id, text=message)
            execute_query('UPDATE chatrooms SET last_voting_notification = ? WHERE chat_id = ?', [now, chat_id])
            chatrooms[chat_id][2] = now

def vote(update, context):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    if chat_id in chatrooms and is_voting_time(chat_id):
        try:
            auswahl = int(update.message.text.strip())
            if auswahl >= 1 and auswahl <= len(locations[chat_id]):
                execute_query('DELETE FROM votings WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
                execute_query('INSERT INTO votings (chat_id, member_id, member_name, location_id) VALUES (?, ?, ?, ?)', [chat_id, user_id, user_name, auswahl])
                location = execute_select('SELECT location FROM locations WHERE chat_id = ? AND l_id = ?', [chat_id, auswahl])[0]
                update.message.reply_text(u'%s hast für %s gestimmt' % (update.message.from_user.first_name, location[0]))
        except ValueError:
            a = 0

######
## Bot Stuff. Init, Mappen der handler/methoden
######

updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher
jobqueue = updater.job_queue

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# Job jede Minute
job_minute = jobqueue.run_repeating(notifier, interval=600, first=0)

# Fuegt eine Location zu den moeglichen Stammtischzielen hinzu
add_handler = CommandHandler('add', add_location)
dispatcher.add_handler(add_handler)

# Listet alle Stammtischzielen
list_handler = CommandHandler('list', list_locations)
dispatcher.add_handler(list_handler)

# Setzt den Stammtischtag
stammtischtag_handler = CommandHandler('stammtischtag', set_stammtischtag)
st_handler = CommandHandler('st', set_stammtischtag)
dispatcher.add_handler(stammtischtag_handler)
dispatcher.add_handler(st_handler)

# Hilfetext anzeigen
help_handler = CommandHandler('help', help)
dispatcher.add_handler(help_handler)

# Eventhandler, wenn der Bot einem Chat hinzugefuegt wird
dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, new_member))

#  Eventhandler, wenn der Bot aus einem Chat entfernt wird
dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, left_member))

# Echo handler
vote_handler = MessageHandler(Filters.group, vote)
dispatcher.add_handler(vote_handler)

updater.start_polling()

# Allen chats sagen, dass der Bot Online ist
#for chatid in chatrooms:
#   updater.bot.send_message(chat_id=int(chatid), text='Ich bin Online!')

updater.idle()
