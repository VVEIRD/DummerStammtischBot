#!/usr/bin/env python
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

os.environ['TZ'] = 'Europe/Berlin'

TIME_ZONE_MOD=+2

TOKEN = sys.argv[1]

DEFAULT_STAMMTISCHTAG = 3

MAX_LOCATIONS = 30

TAGE = {1 : "Montag", 2 : "Dienstag", 3 : "Mittwoch", 4 : "Donnerstag", 5 : "Freitag", 6 : "Samstag", 7 : "Sonntag"}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

conn = sqlite3.connect('DummerStammtischBot.db')

c = conn.cursor()

def add_column_if_not_exists(c, table_name, new_column, new_column_type):
    tab_exists=False
    
    for row in c.execute('SELECT name FROM sqlite_master WHERE type= ? AND name = ?', ['table', table_name]):
        tab_exists=True
    
    if tab_exists:
        columns = [i[1] for i in c.execute('PRAGMA table_info(' + str(table_name) + ')')]
        if new_column not in columns:
            c.execute('ALTER TABLE ' + str(table_name) + ' ADD COLUMN ' + str(new_column) + ' ' + str(new_column_type))


# Create table
c.execute('''CREATE TABLE IF NOT EXISTS chatrooms
             (chat_id INTEGER,
                stammtischtag INTEGER,
                last_notified INTEGER,
                last_voting_notification INTEGER,
                last_organizer INTEGER
              )''')

# Add last_organizer for existing databases
add_column_if_not_exists(c, 'chatrooms', 'last_organizer', 'INTEGER')

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

c.execute('''CREATE TABLE IF NOT EXISTS "voiced" (
    "chat_id"    INTEGER,
    "member_id"    INTEGER,
    PRIMARY KEY("chat_id","member_id")
)''')

c.execute('''CREATE TABLE IF NOT EXISTS "member_credits" (
    "chat_id"      INTEGER,
    "member_id"    INTEGER,
    "credits"      INTEGER,
    PRIMARY KEY("chat_id","member_id")
)''')



######
## Liste mit den Locations fuer den Stammtisch
######

def load_locations():
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    locations = {}
    print('Lade Locations...')
    print('-----------------------------------')
    for row in c.execute('SELECT chat_id, l_id, location FROM locations'):
        if row[0] not in locations:
            print ('Chat ID: %s' % (str(row[0])))
            print('-----------------------------------')
            locations[row[0]] = []
        locations[row[0]].append((row[1], row[2]))
        print(u'Location hinzugefuegt: ID: %d, %d' % (row[0], row[1]) )
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
    for row in c.execute('SELECT chat_id, stammtischtag, last_notified, last_voting_notification, last_organizer FROM chatrooms'):
        chatrooms[row[0]] = [row[1],row[2], row[3], row[4]]
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

# Fuehrt ein Query aus, liefert keine Daten zurueck
def execute_query(query, args):
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    c.execute(query, args)
    conn.commit()
    conn.close()

# Fuert ein Query aus, liefert das Resultat als 2D-Array zurueck
def execute_select(query, args):
    conn = sqlite3.connect('DummerStammtischBot.db')
    c = conn.cursor()
    result = []
    for row in c.execute(query, args):
        result.append(row)
    conn.close()
    return result

# Fuegt einen neuen Gruppenchat hinzu, in dem der Bot hinzugefuegt wurde
def add_chatroom(chat_id):
    if chat_id not in chatrooms:
        chatrooms[chat_id] = [DEFAULT_STAMMTISCHTAG, 0, 0]
        print('New chatroom: ' + str(chat_id))
        execute_query('INSERT INTO chatrooms (chat_id, stammtischtag, last_notified, last_voting_notification) VALUES (?, ?, 0, 0)',  [chat_id, chatrooms[chat_id][0]])

# Entfernt alle Daten ueber einen Gruppenchat, asu dem der Bot entfernt wurde
def remove_chatroom(chat_id):
    if chat_id in chatrooms:
        print('Removed from Chat: ' + str(chat_id))
        chatrooms.pop(chat_id, None)
        locations.pop(chat_id, None)
        execute_query('DELETE FROM chatrooms WHERE chat_id = ?', [chat_id])
        execute_query('DELETE FROM votings WHERE chat_id = ?', [chat_id])
        execute_query('DELETE FROM locations WHERE chat_id = ?', [chat_id])
        print('Removed from chatroom: %s' % chat_id)

def start(update, context):
    add_chatroom(update.message.chat.id)
    context.bot.send_message(chat_id=update.message.chat_id, text="I'm a bot, please talk to me!")

# Prueft ob der User der Nachricht der Admin oder der Ersteller ist.
#  Bei beiden liefert er True zurueck
def has_admin(update, context):
    chat_id = update.message.chat.id
    user = context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    is_admin = 'administrator' == user.status
    is_creator = 'creator' == user.status
    return is_admin or is_creator

# Prueft ob der aufrufende Benutzer von einem Admin voice erhalten hat
#  Falls ja, kann dieser User die erweiterten Funktionen des Bots nutzen
def has_voice(update, context):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    is_voiced = execute_select('SELECT 1 FROM voiced WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
    return len(is_voiced) > 0 

# Erteilt einem Benutzer Voice. Darf nur von Admins ausgefuehrt werden.
def voice(update, context):
    chat_id = update.message.chat.id
    is_admin = has_admin(update, context)
    if not is_admin:
        update.message.reply_text(u'Nur Admins können diese Funktion benutzen')
        return
    for mention in update.message.entities:
        if mention.user is not None:
            user_id = mention.user.id
            user_name = mention.user.first_name
            execute_query('DELETE FROM voiced WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
            execute_query('INSERT INTO voiced (chat_id, member_id) VALUES (?, ?)', [chat_id, user_id])
            update.message.reply_text(u'%s wurde authorisiert' % (user_name))

# Entzieht einem User voice. Darf nur von einem Admin gemacht werden
def revoke(update, context):
    chat_id = update.message.chat.id
    is_admin = has_admin(update, context)
    if not is_admin:
        update.message.reply_text(u'Nur Admins können diese Funktion benutzen')
        return
    for mention in update.message.entities:
        if mention.user is not None:
            user_id = mention.user.id
            user_name = mention.user.first_name
            execute_query('DELETE FROM voiced WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
            update.message.reply_text(u'%s kann die erweiterten Funktionen nicht mehr nutzen' % (user_name))

# Fuegt einen ort zu den Stammtischen hinzu. Darf nut von Usern mit voice oder Admins gemacht werden
def add_location(update, context):
    global locations
    add_chatroom(update.message.chat.id)
    chat_id = update.message.chat.id
    location = ' '.join(context.args).strip()
    is_admin = has_admin(update, context)
    is_voiced = has_voice(update, context)
    if not is_admin and not is_voiced:
        update.message.reply_text(u'Du hast keine Berechtigung einen Ort hinzuzufügen, frage einen Admin ob er dich dazu berechtigt.')
        return
    if chat_id not in locations:
        locations[chat_id] = []
    if location and location not in locations[chat_id] and len(locations) <= MAX_LOCATIONS:
        execute_query('''INSERT INTO locations (chat_id, l_id, location) VALUES (?, Ifnull((SELECT max(l_id)+1 FROM locations WHERE chat_id = ?), 1), ?)''', (chat_id, chat_id, location))
        locations = load_locations()
        update.message.reply_text('Das Ziel ' + location + u' wurde hinzugefügt')
    elif len(locations) > MAX_LOCATIONS:
        update.message.reply_text('Ihr habt das Limit von %s Locations erreicht, sorry!')

# Listet alle Orte, die für den Stammtisch verfügbar sind, auf.
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

# Loescht einen Ort. Darf nut von Admins gemacht werden
def del_location(update, context):
    global locations
    add_chatroom(update.message.chat.id)
    chat_id = update.message.chat.id
    location_id = int(' '.join(context.args).strip())
    is_admin = has_admin(update, context)
    if not is_admin:
        update.message.reply_text(u'Du hast keine Berechtigung einen Ort zu löschen, frage einen Admin ob den Ort für dich löscht.')
        return
    if chat_id not in locations:
        locations[chat_id] = []
    loc_exist = False
    loc_name = ''
    for loc in locations[chat_id]:
        if loc[0] == location_id:
            loc_exist = True
            loc_name = loc[1]
            break
    if location_id and loc_exist:
        execute_query('''DELETE FROM locations WHERE chat_id = ? AND l_id = ?''', (chat_id, location_id))
        locations = load_locations()
        update.message.reply_text('Das Ziel ' + str(location_id) + '. ' + loc_name + u' wurde gelöscht')
    else:
        update.message.reply_text('Die Location existiert nicht (mehr)!')

# Setzt den Tag des Stammtisches. Davon hängt ab wann abgestimmt wird. Duerfen nur Admins machen.
def set_stammtischtag(update, context):
    chat_id = update.message.chat.id
    from_user = context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    is_admin = has_admin(update, context)
    if not is_admin:
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


# Zeigt alle verfuegbaren Funktionen an
def help(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=u'''Ich bin der StammtischBot!\r\n
Folgende Befhele stehen euch zur Auswahl:

[Admins]
 /stammtischtag oder /st: Legt den Tag des Stammtischs fest
 /voice [1..x]: Der angegebene Benutzer kann die erweiterte Funktionen nutzen
 /revoke [1..x]: Entzieht den angegebenen Benutzern die Rechte auf die erweiterten funktionen.
[Erweiterte Funktionen]
 /add: Ein Stammtischziel hinzufügen
 /del: Löscht einen Ort

[Alle]
 /list: Alle Stammtischziele anzeigen
 /help: Diese Nachricht anzeigen
 /not_today: Der aktuelle Organisator kann die Orge eine Stunde nach der Entscheidung abgeben''')


# Gibt aus, ob der Chat im Abstimmzeitraum befindet
def is_voting_time(chat_id, message_date):
    # Weekday of Message
    weekday = message_date.weekday()+1
    # Hour of message
    hour = message_date.hour+TIME_ZONE_MOD
    # Am Tag vor dem Stammtisch soll abgestimmt werden
    dayToNotifyAt = chatrooms[chat_id][0]-1
    # Zeitpunkt an dem das letztre Voting gestartet wurde
    lastNotified = chatrooms[chat_id][1]
    # Zeitpunkt an dem das letztre Voting beendet wurde
    lastVotingNotified = chatrooms[chat_id][2]
    # Wir wollen am Vortag zwischen 8 und 18 Uhr voten
    print('--------------------------------------------------')
    print('Check is voting time')
    print('--------------------------------------------------')
    print('Weekday: %d' % (weekday))
    print('Hour: %d' % (hour))
    print('Day to notify: %d' % (dayToNotifyAt))
    print('Last voting: %d' % (lastNotified))
    print('Last voting ended: %d' % (lastVotingNotified))
    print('Notify today: %s' % (str(dayToNotifyAt == weekday and hour >= 8 and hour < 18)))
    print('--------------------------------------------------')
    return dayToNotifyAt == weekday and hour >= 8 and hour < 18

# Informiert den Chat ueber diverse Dinge
def notifier(context):
    for chat_id in chatrooms:
        now = int(time.time())
        weekday = datetime.datetime.today().weekday()+1
        hour = datetime.datetime.now().hour
        print('Hour: %s' % (hour))
        # Am Tag vor dem Stammtisch soll abgestimmt werden
        dayToNotifyAt = chatrooms[chat_id][0]-1
        # Zeitpunkt an dem das letztre Voting gestartet wurde
        lastNotified = chatrooms[chat_id][1]
        # Zeitpunkt an dem das letztre Voting beendet wurde
        lastVotingNotified = chatrooms[chat_id][2]
        # Wir wollen am Vortag installieren nur einmal pro Woche nach 8 Uhr
        if dayToNotifyAt == weekday and lastNotified+518400 < now and hour >= 8:
            print("Notifying %s" % chat_id)
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
            last_organizer = chatrooms[chat_id][3]
            conn = sqlite3.connect('DummerStammtischBot.db')
            c = conn.cursor()
            message = 'Die Abstimmungszeit ist vorbei! Ihr habt wie folgt abgestimmt:\n\n'
            i = 1
            for row in c.execute('select (SELECT location FROm locations l WHERE l.l_id = v.location_id AND l.chat_id = v.chat_id) location, count(*) c FROM votings v WHERE chat_id = ? GROUP BY location_id ORDER BY c DESC', [chat_id]):
                message += '%s. %s (%s Stimmen)\n' % (i, row[0], row[1])
                i += 1
            organisierer = c.execute('SELECT member_name, member_id FROM votings v WHERE chat_id = ? AND member_id IN (SELECT member_id FROM votings v2 WHERE chat_id = ? AND member_id IS NOT ? ORDER BY RANDOM() LIMIT 1)' , [chat_id, chat_id, last_organizer]).fetchone()
            message += '\n%s darf diese Woche den Stammtisch organisieren' % organisierer[0]
            org_member_id = organisierer[1]
            context.bot.send_message(chat_id=chat_id, text=message)
            execute_query('UPDATE chatrooms SET last_voting_notification = ?, last_organizer = ? WHERE chat_id = ?', [now, org_member_id, chat_id])
            # If User was never organizer, they get 4 credits
            credits = execute_select('SELECT credits FROM member_credits WHERE chat_id = ? AND member_id = ?', [chat_id, member_id])
            if len(credits) == 0:
                execute_query('INSERT INTO member_credits(chat_id, member_id, credits) VALUES (?, ?, ?)', [chat_id, member_id, 4])
            # Add a credit to the member
            execute_query('UPDATE member_credits SET credits = credits+1 WHERE chat_id = ? AND member_id = ?', [chat_id, member_id])
            chatrooms[chat_id][2] = now
            chatrooms[chat_id][3] = org_member_id

# Abstimmfunktion, der benutzer muss nur eine valide Zahl in den Chat eintippen, damit er abstimmt.
# Er wird vom Bot informiert, wenn er abgestimmt hat.
def vote(update, context):
    print('------------------------------------')
    print ('Voting...')
    print('------------------------------------')
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    message_date = update.message.date
    print(u'%s hat mit %s abgestimmt' % (user_name, update.message.text))
    print('Is voting time: %s' % (str(is_voting_time(chat_id, message_date))))
    if chat_id in chatrooms and is_voting_time(chat_id, message_date):
        print ('Chatgroup is included')
        try:
            auswahl = int(update.message.text.strip())
            valid_selection = False
            for l in locations[chat_id]:
                if auswahl == l[0]:
                    valid_selection = True
            if auswahl >= 1 and valid_selection:
                print('Auswahl ist vorhanden')
                execute_query('DELETE FROM votings WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
                execute_query('INSERT INTO votings (chat_id, member_id, member_name, location_id) VALUES (?, ?, ?, ?)', [chat_id, user_id, user_name, auswahl])
                location = execute_select('SELECT location FROM locations WHERE chat_id = ? AND l_id = ?', [chat_id, auswahl])[0]
                print('Location ist %s' % (location[0]))
                update.message.reply_text(u'%s hat für %s gestimmt' % (update.message.from_user.first_name, location[0]))
        except ValueError:
            a = 0
    print('------------------------------------')

# Prueft ob der aufrufende Benutzer genug credits zum aufrufen der ot_today funktion hat
#  Falls ja, kann dieser User die erweiterten Funktionen des Bots nutzen
def has_enought_member_credits(update, context):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    credits = execute_select('SELECT credits FROM member_credits WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
    # If User was never organizer, they get 4 credits
    if len(credits) == 0:
        execute_query('INSERT INTO member_credits(chat_id, member_id, credits) VALUES (?, ?, ?)', [chat_id, member_id, 4])
        credits = execute_select('SELECT credits FROM member_credits WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
    credits = credits.fetchone()[0]
    enougth_credits = False
    if credits >= 3:
        enougth_credits = True
        execute_query('UPDATE member_credits SET credits = credits-3 WHERE chat_id = ? AND member_id = ?', [chat_id, member_id])
    return enougth_credits


# Gibt aus, ob der /nottoday Befehl vom Organisator durchgeführt werden kann
def is_nottoday_time(chat_id, message_date):
    # Weekday of Message
    weekday = message_date.weekday()+1
    # Hour of message
    hour = message_date.hour
    # Am Tag vor dem Stammtisch soll abgestimmt werden
    dayToNotifyAt = chatrooms[chat_id][0]-1
    # Zeitpunkt an dem das letztre Voting gestartet wurde
    lastNotified = chatrooms[chat_id][1]
    # Zeitpunkt an dem das letztre Voting beendet wurde
    lastVotingNotified = chatrooms[chat_id][2]
    # Wir wollen am Vortag zwischen 8 und 18 Uhr voten
    return dayToNotifyAt == weekday and hour >= 18 and hour <= 19

# Funktion wenn der Organisator heute NICHT organisieren will
def not_today(update, context):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    message_date = update.message.date
    if chat_id in chatrooms and is_nottoday_time(chat_id, message_date) and user_id == chatrooms[chat_id][3]:
        if has_enought_member_credits(update, context):
            update.message.reply_text(u'%s möchte heute nicht den Stammtisch organisieren, es wird ein neuer Organisator gewählt.' % (update.message.from_user.first_name) )
            last_organizer = chatrooms[chat_id][3]
            conn = sqlite3.connect('DummerStammtischBot.db')
            c = conn.cursor()
            message = 'Die Abstimmungszeit ist vorbei! Ihr habt wie folgt abgestimmt:\n\n'
            i = 1
            for row in c.execute('select (SELECT location FROm locations l WHERE l.l_id = v.location_id AND l.chat_id = v.chat_id) location, count(*) c FROM votings v WHERE chat_id = ? GROUP BY location_id ORDER BY c DESC', [chat_id]):
                message += '%s. %s (%s Stimmen)\n' % (i, row[0], row[1])
                i += 1
            organisierer = c.execute('SELECT member_name, member_id FROM votings v WHERE chat_id = ? AND member_id IN (SELECT member_id FROM votings v2 WHERE chat_id = ? AND member_id IS NOT ? ORDER BY RANDOM() LIMIT 1)' , [chat_id, chat_id, last_organizer]).fetchone()
            message += '\n%s darf diese Woche den Stammtisch organisieren' % org[0]
            org_member_id = org[1]
            context.bot.send_message(chat_id=chat_id, text=message)
            execute_query('UPDATE chatrooms SET last_voting_notification = ?, last_organizer = ? WHERE chat_id = ?', [now, org_member_id, chat_id])
            # If User was never organizer, they get 4 credits
            credits = execute_select('SELECT credits FROM member_credits WHERE chat_id = ? AND member_id = ?', [chat_id, user_id])
            if len(credits) == 0:
                execute_query('INSERT INTO member_credits(chat_id, member_id, credits) VALUES (?, ?, ?)', [chat_id, member_id, 4])
            # Add a credit to the member
            execute_query('UPDATE member_credits SET credits = credits+1 WHERE chat_id = ? AND member_id = ?', [chat_id, member_id])
            chatrooms[chat_id][2] = now
            chatrooms[chat_id][3] = org_member_id
        else:
            update.message.reply_text(u'Du hast leider nicht genug Credits um die Organisation abzugeben!')
    elif chat_id in chatrooms and is_nottoday_time(chat_id, message_date):
        update.message.reply_text(u'Der Zeitraum die Organisation abzugeben ist leider schon vorbei!')
    elif chat_id in chatrooms and user_id != chatrooms[chat_id][3]:
        update.message.reply_text(u'Du Organisierst den Stammtisch heute gar nicht!')
    else:
        update.message.reply_text(u'Etwas ist schiefgegangen?!?!!?')

######
## Bot Stuff. Init, Mappen der handler/methoden
######

updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher
jobqueue = updater.job_queue

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# Job jede Minute
job_minute = jobqueue.run_repeating(notifier, interval=600, first=20)

# Fuegt eine Location zu den moeglichen Stammtischzielen hinzu
add_handler = CommandHandler('add', add_location)
dispatcher.add_handler(add_handler)

# Loescht eine Location
del_handler = CommandHandler('del', del_location)
dispatcher.add_handler(del_handler)

# Listet alle Stammtischzielen
list_handler = CommandHandler('list', list_locations)
dispatcher.add_handler(list_handler)

# Benutzer mehr Berechtigung geben
voice_handler = CommandHandler('voice', voice)
dispatcher.add_handler(voice_handler)

# Benutzer mehr Berechtigung geben
revoke_handler = CommandHandler('revoke', revoke)
dispatcher.add_handler(revoke_handler)

# Organisator gibt orga ab
not_today_handler = CommandHandler('not_today', not_today)
dispatcher.add_handler(not_today_handler)

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
